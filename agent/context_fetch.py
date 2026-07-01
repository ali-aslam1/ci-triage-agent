import os
import json
import base64
import ast
import re
import urllib.parse
from typing import Optional, Dict, List, Any

from ingest.fetch import make_request
from agent.correlate import normalize_path, is_repo_file

FILE_LINE_RE = re.compile(r'File "([^"]+)", line (\d+)(?:, in (\w+))?')
FAILED_LINE_RE = re.compile(r'FAILED\s+([^\s:]+(?:::[^\s:]+)+)')
DEF_RE = re.compile(r'def\s+(\w+)\s*\(')


def _extract_candidates_from_lines(lines: List[str]) -> List[tuple]:
    """
    Scans a list of log lines and extracts (filepath, line_num, func_name) tuples
    by matching File/line stack trace patterns and pytest FAILED summary lines.
    """
    candidates = []
    for line in lines:
        file_match = FILE_LINE_RE.search(line)
        if file_match:
            filepath = file_match.group(1)
            line_num = int(file_match.group(2))
            func_name = file_match.group(3)
            candidates.append((filepath, line_num, func_name))

        failed_match = FAILED_LINE_RE.search(line)
        if failed_match:
            parts = failed_match.group(1).split("::")
            filepath = parts[0]
            func_name = parts[-1] if len(parts) > 1 else None
            candidates.append((filepath, None, func_name))
    return candidates


def parse_stack_trace(log_text: str, evidence_lines: List[str]) -> Optional[Dict[str, Any]]:
    """
    Parses failure logs and evidence lines to locate the failing file path
    and function name.

    Args:
        log_text (str): Full failure log content.
        evidence_lines (list): Verbatim key log lines from the classification result.

    Returns:
        dict: A dict containing 'file_path' and 'function_name' (or None) if found, else None.
    """
    log_lines = log_text.splitlines()

    # 1. Search in evidence_lines first (high signal, focused)
    candidates = _extract_candidates_from_lines(evidence_lines)

    # 2. Fallback: scan the full log text
    if not candidates:
        candidates = _extract_candidates_from_lines(log_lines)

    # 3. Filter candidates to repository files only, resolve missing function name
    for filepath, line_num, func_name in candidates:
        norm_path = normalize_path(filepath)
        if not is_repo_file(norm_path):
            continue

        # If function name is missing (e.g. collection error), search nearby lines for a def
        if not func_name:
            # Check evidence lines first
            for ev_line in evidence_lines:
                def_match = DEF_RE.search(ev_line)
                if def_match:
                    func_name = def_match.group(1)
                    break

            # Then scan log lines near the matched file/line reference
            if not func_name and line_num is not None:
                for idx, log_line in enumerate(log_lines):
                    if filepath in log_line and f"line {line_num}" in log_line:
                        for offset in range(1, 6):
                            if idx + offset < len(log_lines):
                                def_match = DEF_RE.search(log_lines[idx + offset])
                                if def_match:
                                    func_name = def_match.group(1)
                                    break
                        if func_name:
                            break

        return {
            "file_path": norm_path,
            "function_name": func_name
        }

    return None


def fetch_function_source(repo: str, commit_sha: str, file_path: str, function_name: Optional[str], pat: str) -> Optional[str]:
    """
    Fetches the source code of the specified file, attempting to isolate the specific
    failing function.

    Args:
        repo (str): Repository name in 'owner/repo_name' format.
        commit_sha (str): Commit SHA to fetch the content from.
        file_path (str): Relative file path in the repository.
        function_name (str, optional): The name of the function to extract.
        pat (str): GitHub Personal Access Token.

    Returns:
        str: Extracted function source, or fallback source content, or None on API failure.
    """
    if '/' not in repo:
        return None

    owner, repo_name = repo.split('/', 1)
    encoded_path = urllib.parse.quote(file_path)
    url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/{encoded_path}?ref={commit_sha}"

    try:
        body_bytes, _ = make_request(url, pat)
        data = json.loads(body_bytes.decode('utf-8'))
        content_b64 = data.get("content", "")
        if not content_b64:
            return None
        file_content = base64.b64decode(content_b64).decode('utf-8', errors='replace')
    except Exception as e:
        print(f"[WARNING] Failed to fetch context file '{file_path}' from GitHub API: {e}")
        return None

    lines = file_content.splitlines()

    # Fallback: no function name specified — return first 100 lines
    if not function_name:
        return "\n".join(lines[:100])

    # Strategy 1: AST walk (primary, for syntactically valid Python)
    try:
        tree = ast.parse(file_content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
                start_line = node.lineno - 1
                end_lineno = getattr(node, 'end_lineno', None) or (node.lineno + 30)
                end_line = min(end_lineno, len(lines))
                return "\n".join(lines[start_line:end_line])
    except SyntaxError:
        # File is broken (Pattern 1 — the file itself has a syntax error).
        # Fall through to string-search.
        pass

    # Strategy 2: String-search fallback (broken files or non-Python)
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith(f"def {function_name}(") or stripped.startswith(f"async def {function_name}("):
            return "\n".join(lines[idx:min(idx + 30, len(lines))])

    # Final fallback: return first 100 lines
    return "\n".join(lines[:100])


def fetch_context_for_run(log_text: str, evidence_lines: List[str], repo: str, commit_sha: str, pat: Optional[str] = None) -> Optional[str]:
    """
    Combined helper that parses stack trace and fetches context file content.
    """
    if not pat:
        pat = os.getenv("GITHUB_PAT")
    if not pat or pat == 'your_personal_access_token_here':
        return None

    trace_info = parse_stack_trace(log_text, evidence_lines)
    if not trace_info:
        return None

    file_path = trace_info["file_path"]
    function_name = trace_info["function_name"]

    source = fetch_function_source(
        repo=repo,
        commit_sha=commit_sha,
        file_path=file_path,
        function_name=function_name,
        pat=pat
    )

    if not source:
        return None

    header = f"CONTEXT — {file_path}"
    if function_name:
        header += f" :: {function_name}"

    return f"{header}\n---\n{source}"

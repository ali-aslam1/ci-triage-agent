import re

def normalize_path(filepath: str) -> str:
    """
    Normalizes file paths by converting backslashes to forward slashes
    and stripping runner-specific workspace prefixes.
    """
    if not filepath:
        return ""
    # Normalize separators
    normalized = filepath.replace('\\', '/')
    # Strip runner workspace prefixes (e.g. /home/runner/work/repo/repo/ or d:/a/repo/repo/)
    normalized = re.sub(r'^/home/runner/work/[^/]+/[^/]+/', '', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'^[a-zA-Z]:/a/[^/]+/[^/]+/', '', normalized, flags=re.IGNORECASE)
    return normalized

def is_repo_file(filepath: str) -> bool:
    """
    Checks if a filepath belongs to the repository code, filtering out
    standard library, virtual environment, third-party library paths,
    and non-code files (like workflows, requirements, metadata).
    """
    if not filepath:
        return False
    norm = normalize_path(filepath)
    
    # Exclude external/library files
    exclude_patterns = [
        r'site-packages',
        r'lib/python\d\.\d+',
        r'hostedtoolcache',
        r'<frozen',
        r'node_modules',
        r'^/opt/',
        r'^/usr/',
    ]
    if any(re.search(pat, norm, re.IGNORECASE) for pat in exclude_patterns):
        return False
        
    # Exclude typical config/documentation/workflow/meta files to avoid false matches
    meta_patterns = [
        r'\.github/',
        r'\.git',
        r'\.yml$',
        r'\.yaml$',
        r'\.json$',
        r'\.toml$',
        r'\.md$',
        r'\.txt$',
        r'\.lock$',
        r'\.cfg$',
        r'\.ini$',
    ]
    if any(re.search(pat, norm, re.IGNORECASE) for pat in meta_patterns):
        return False
        
    # Ensure it's not an absolute path
    if norm.startswith('/') or re.match(r'^[a-zA-Z]:/', norm):
        return False
        
    return True

def correlate_run(cleaned_log: str, changed_files: list[str]) -> dict:
    """
    Correlates a cleaned log with changed files by executing a substring match.
    Returns any_file_in_diff, matched_files, and hint.
    """
    if not changed_files:
        return {
            "any_file_in_diff": False,
            "matched_files": [],
            "hint": "None of the changed repository files were found in the failure log. This strongly hints at a flaky test, dependency issue, environment mismatch, or orchestration/infrastructure failure."
        }
    
    # 1. Filter changed_files to repository files
    filtered_files = [f for f in changed_files if is_repo_file(f)]
    
    # 2. Normalize path separators in cleaned_log to forward slashes for cross-platform robustness
    cleaned_log_normalized = cleaned_log.replace('\\', '/')
    
    # 3. Substring matching
    matched_files = []
    for f in filtered_files:
        norm_f = normalize_path(f)
        if norm_f in cleaned_log_normalized:
            matched_files.append(f)
            
    any_file_in_diff = len(matched_files) > 0
    
    if any_file_in_diff:
        hint = "At least one changed file was found in the failure log stack traces or references. This indicates a potential code regression or syntax error in the modified files."
    else:
        hint = "None of the changed repository files were found in the failure log. This strongly hints at a flaky test, dependency issue, environment mismatch, or orchestration/infrastructure failure."
        
    return {
        "any_file_in_diff": any_file_in_diff,
        "matched_files": matched_files,
        "hint": hint
    }

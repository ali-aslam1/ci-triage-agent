import os
import sys
import json
import zipfile
import io
import urllib.request
import urllib.error

def load_env():
    """Manually parse .env file if it exists to keep script zero-dependency."""
    env_path = '.env'
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    # Strip quotes if present
                    val = val.strip().strip("'").strip('"')
                    os.environ[key.strip()] = val

def make_request(url, pat, accept='application/vnd.github+json'):
    """Make HTTP GET request to GitHub API with Authentication headers."""
    req = urllib.request.Request(url)
    req.add_header('Authorization', f'Bearer {pat}')
    req.add_header('Accept', accept)
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    req.add_header('User-Agent', 'CI-Triage-Agent')
    
    try:
        with urllib.request.urlopen(req) as response:
            return response.read(), response.info()
    except urllib.error.HTTPError as e:
        # Re-raise with some context if possible
        raise e
    except urllib.error.URLError as e:
        raise e

def fetch_run(run_id, repo=None, owner=None, pat=None):
    """
    Pulls workflow run logs, triggering commit SHA, and comparing diff from GitHub API.
    
    Args:
        run_id (int or str): The GitHub Actions workflow run ID.
        repo (str, optional): The repository name. If not provided, it will search the 
                             repositories in the GITHUB_REPOS environment variable.
        owner (str, optional): The repository owner. If not provided, GITHUB_OWNER will be used.
        pat (str, optional): The GitHub Personal Access Token. If not provided, GITHUB_PAT will be used.
        
    Returns:
        dict: A dictionary containing:
            - 'log_text': Combined log content from all unzipped log files.
            - 'commit_sha': The SHA of the triggering commit.
            - 'diff': The unified diff of the changes (comparing against PR base or parent commit).
    """
    load_env()
    
    # Resolve PAT
    if not pat:
        pat = os.getenv('GITHUB_PAT')
    if not pat or pat == 'your_personal_access_token_here':
        raise ValueError("GitHub PAT (GITHUB_PAT) is not configured in .env or arguments.")
        
    # Resolve Owner
    if not owner:
        owner = os.getenv('GITHUB_OWNER')
    if not owner:
        raise ValueError("GitHub Owner (GITHUB_OWNER) is not configured in .env or arguments.")
        
    run_id_str = str(run_id).strip()
    
    run_data = None
    resolved_repo = None
    
    # Resolve repo or search configured repos
    if repo:
        run_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id_str}"
        try:
            body_bytes, _ = make_request(run_url, pat)
            run_data = json.loads(body_bytes.decode('utf-8'))
            resolved_repo = repo
        except Exception as e:
            raise ValueError(f"Failed to fetch run details for run ID {run_id_str} in repository {owner}/{repo}: {e}")
    else:
        repos_str = os.getenv('GITHUB_REPOS')
        if not repos_str:
            raise ValueError("No repository specified and GITHUB_REPOS is not configured in .env.")
        repos = [r.strip() for r in repos_str.split(',') if r.strip()]
        
        for r in repos:
            run_url = f"https://api.github.com/repos/{owner}/{r}/actions/runs/{run_id_str}"
            try:
                body_bytes, _ = make_request(run_url, pat)
                run_data = json.loads(body_bytes.decode('utf-8'))
                resolved_repo = r
                break  # Successfully found the repository containing the run
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue  # Try next repository
                # For other errors, we can log it but continue searching
                print(f"Warning: HTTP {e.code} error when searching repo {r}: {e.reason}", file=sys.stderr)
            except Exception as e:
                print(f"Warning: Error when searching repo {r}: {e}", file=sys.stderr)
                
        if not run_data:
            raise ValueError(f"Run ID {run_id_str} not found in any of the configured repositories: {repos}")
            
    # 1. Triggering commit SHA
    commit_sha = run_data.get('head_sha')
    if not commit_sha:
        # Fallback to check head_commit structure if head_sha is missing
        head_commit = run_data.get('head_commit', {})
        commit_sha = head_commit.get('id')
        
    # 2. Retrieve Logs
    log_text = ""
    log_url = f"https://api.github.com/repos/{owner}/{resolved_repo}/actions/runs/{run_id_str}/logs"
    try:
        log_zip_bytes, _ = make_request(log_url, pat)
        with zipfile.ZipFile(io.BytesIO(log_zip_bytes)) as z:
            # Sort files so logs follow consistent/sequential order
            file_names = sorted(z.namelist())
            log_parts = []
            for name in file_names:
                # Only read files, skip directories
                if not name.endswith('/'):
                    with z.open(name) as f:
                        try:
                            content = f.read().decode('utf-8', errors='replace')
                            log_parts.append(
                                f"================================================================================\n"
                                f"LOG FILE: {name}\n"
                                f"================================================================================\n"
                                f"{content}\n"
                            )
                        except Exception as decode_err:
                            log_parts.append(f"[Error decoding file {name}: {decode_err}]\n")
            log_text = "".join(log_parts)
    except urllib.error.HTTPError as e:
        log_text = f"Error retrieving logs (HTTP {e.code}: {e.reason}). Logs might have expired or are unavailable."
    except Exception as e:
        log_text = f"Error retrieving/parsing logs: {e}"

    # 3. Determine base and head for comparison diff
    base = None
    head = commit_sha
    
    pull_requests = run_data.get('pull_requests', [])
    if pull_requests:
        # Use pull request base/head
        pr = pull_requests[0]
        base = pr.get('base', {}).get('sha')
        head = pr.get('head', {}).get('sha') or commit_sha
    else:
        # Push event or other event. Find parent commit of commit_sha
        if commit_sha:
            commit_url = f"https://api.github.com/repos/{owner}/{resolved_repo}/commits/{commit_sha}"
            try:
                commit_bytes, _ = make_request(commit_url, pat)
                commit_data = json.loads(commit_bytes.decode('utf-8'))
                parents = commit_data.get('parents', [])
                if parents:
                    base = parents[0].get('sha')
            except Exception as e:
                print(f"Warning: Failed to fetch parent commit for {commit_sha}: {e}", file=sys.stderr)

    # 4. Pull comparison diff
    diff_text = ""
    if base and head:
        compare_url = f"https://api.github.com/repos/{owner}/{resolved_repo}/compare/{base}...{head}"
        try:
            diff_bytes, _ = make_request(compare_url, pat, accept='application/vnd.github.diff')
            diff_text = diff_bytes.decode('utf-8', errors='replace')
        except Exception as e:
            diff_text = f"Error retrieving diff from {base} to {head}: {e}"
    else:
        diff_text = "No base commit found to compare against (possibly a root commit or repository setup issue)."

    return {
        "log_text": log_text,
        "commit_sha": commit_sha,
        "diff": diff_text
    }

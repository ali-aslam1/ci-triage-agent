import os
import json
from typing import Optional

from ingest.fetch import make_request
from ingest.clean import extract_changed_files
from agent.correlate import is_repo_file

def check_flaky_override(run_id: str, repo: str, pat: Optional[str] = None) -> bool:
    """
    Checks if this run can be hard-overridden as Flaky based on adjacent runs.
    
    Checks if a run of the same workflow (run_number N-1 or N+1) succeeded,
    and if there were no changes to relevant repository code files between them.
    
    Args:
        run_id (str): The run ID of the current failed run.
        repo (str): The repository name in 'owner/repo_name' format.
        pat (str, optional): The GitHub Personal Access Token.
        
    Returns:
        bool: True if flaky override conditions are met, False otherwise.
    """
    if not pat:
        pat = os.getenv("GITHUB_PAT")
    if not pat or pat == 'your_personal_access_token_here':
        print("[WARNING] GITHUB_PAT not configured. Skipping flaky override check.")
        return False
        
    if '/' not in repo:
        print(f"[WARNING] Invalid repo format '{repo}'. Expected 'owner/repo'. Skipping flaky check.")
        return False
        
    owner, repo_name = repo.split('/', 1)
    run_id_str = run_id.strip()
    
    print(f"[Flaky Check] Starting flaky override analysis for run {run_id_str} in {repo}...")
    
    # 1. Fetch current run details to get workflow_id, run_number, and head_sha
    try:
        run_url = f"https://api.github.com/repos/{owner}/{repo_name}/actions/runs/{run_id_str}"
        body_bytes, _ = make_request(run_url, pat)
        current_run = json.loads(body_bytes.decode('utf-8'))
    except Exception as e:
        print(f"[WARNING] Failed to fetch current run details from GitHub API: {e}. Proceeding without override.")
        return False
        
    workflow_id = current_run.get("workflow_id")
    current_run_number = current_run.get("run_number")
    current_sha = current_run.get("head_sha")
    
    if not workflow_id or not current_run_number or not current_sha:
        print(f"[WARNING] Missing workflow run details (workflow_id: {workflow_id}, run_number: {current_run_number}, sha: {current_sha}). Skipping flaky check.")
        return False
        
    print(f"[Flaky Check] Current run number: {current_run_number}, SHA: {current_sha}, Workflow ID: {workflow_id}")
    
    # 2. Fetch last 30 workflow runs of the same workflow
    try:
        runs_url = f"https://api.github.com/repos/{owner}/{repo_name}/actions/workflows/{workflow_id}/runs?per_page=30"
        body_bytes, _ = make_request(runs_url, pat)
        runs_data = json.loads(body_bytes.decode('utf-8'))
        workflow_runs = runs_data.get("workflow_runs", [])
    except Exception as e:
        print(f"[WARNING] Failed to fetch workflow runs from GitHub API: {e}. Proceeding without override.")
        return False
        
    # 3. Look for adjacent successful runs (run_number N-1 or N+1)
    adjacent_candidates = []
    for run in workflow_runs:
        r_num = run.get("run_number")
        conclusion = run.get("conclusion")
        # Check if it is adjacent and succeeded
        if r_num in (current_run_number - 1, current_run_number + 1) and conclusion == "success":
            adjacent_candidates.append(run)
            
    if not adjacent_candidates:
        print(f"[Flaky Check] No successful adjacent runs (run_number {current_run_number - 1} or {current_run_number + 1}) found.")
        return False
        
    # 4. Check for diff changes between current run and adjacent successful runs
    for adj_run in adjacent_candidates:
        adj_id = adj_run.get("id")
        adj_num = adj_run.get("run_number")
        adj_sha = adj_run.get("head_sha")
        
        print(f"[Flaky Check] Found successful adjacent run {adj_id} (run_number: {adj_num}, SHA: {adj_sha})")
        
        # If the commit is the exact same, no diff changes at all!
        if current_sha == adj_sha:
            print(f"[Flaky Check] SUCCESS: Run {adj_id} has the exact same commit SHA ({current_sha}). Hard-overriding to Flaky!")
            return True
            
        # Determine older vs newer run to query Compare API correctly
        # Pass older commit as base, newer commit as head
        if current_run_number < adj_num:
            base_sha, head_sha = current_sha, adj_sha
        else:
            base_sha, head_sha = adj_sha, current_sha
            
        print(f"[Flaky Check] Comparing diff from base {base_sha} to head {head_sha}...")
        compare_url = f"https://api.github.com/repos/{owner}/{repo_name}/compare/{base_sha}...{head_sha}"
        
        try:
            diff_bytes, _ = make_request(compare_url, pat, accept='application/vnd.github.diff')
            diff_text = diff_bytes.decode('utf-8', errors='replace')
        except Exception as e:
            print(f"[WARNING] Compare API request failed between {base_sha} and {head_sha}: {e}")
            continue
            
        changed_files = extract_changed_files(diff_text)
        relevant_files = [f for f in changed_files if is_repo_file(f)]
        
        if not relevant_files:
            print(f"[Flaky Check] SUCCESS: No relevant code files changed between current run and adjacent successful run {adj_num}. (Changed files: {changed_files}). Hard-overriding to Flaky!")
            return True
        else:
            print(f"[Flaky Check] Adjacent run {adj_num} has relevant code changes nearby: {relevant_files}")
            
    print("[Flaky Check] Flaky override check finished. No matching successful adjacent runs with clean diffs found.")
    return False

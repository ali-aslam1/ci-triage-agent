import sys
import os
import re

from ingest import (
    fetch_run,
    load_env,
    clean_log,
    init_db,
    save_run,
    extract_changed_files,
    get_run
)

# Regex pattern to parse github repository owner, name, and run ID from Actions URL
URL_PATTERN = re.compile(r'github\.com/([^/]+)/([^/]+)/actions/runs/(\d+)')

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    # Load configuration at startup
    load_env()

    # Resolve database path from environment variable with a default fallback
    db_path = os.getenv("GITHUB_TRIAGE_DB", "triage.db")
    init_db(db_path)

    if len(sys.argv) < 2:
        print("Usage: python run_ingest.py <github_run_url>")
        print("Example: python run_ingest.py https://github.com/ali-aslam1/pdf-ai-research-assistant/actions/runs/28305298829")
        sys.exit(1)
        
    url = sys.argv[1].strip()
    match = URL_PATTERN.search(url)
    if not match:
        print(f"[ERROR] Invalid GitHub Actions Run URL: '{url}'")
        print("URL must match the format: https://github.com/{owner}/{repo}/actions/runs/{run_id}")
        sys.exit(1)
        
    owner = match.group(1)
    repo = match.group(2)
    run_id = match.group(3)
    
    pat = os.getenv('GITHUB_PAT')
    if not pat or pat == 'your_personal_access_token_here':
        print("[ERROR] GITHUB_PAT is not configured in .env or environment.")
        sys.exit(1)
        
    print(f"Parsed Run Details:")
    print(f"  Owner:      {owner}")
    print(f"  Repo:       {repo}")
    print(f"  Run ID:     {run_id}")
    print("Fetching run details from GitHub API...")
    
    try:
        # Fetch raw metadata, logs, and diff
        run_data = fetch_run(run_id, repo=repo, owner=owner, pat=pat)
        
        raw_log = run_data["log_text"]
        commit_sha = run_data["commit_sha"]
        diff_text = run_data["diff"]
        conclusion = run_data["conclusion"]
        
        print("\nAPI Fetch Success:")
        print(f"  Triggering Commit: {commit_sha}")
        print(f"  Run Conclusion:    {conclusion}")
        print(f"  Raw Log Size:       {len(raw_log)} chars")
        print(f"  Diff Size:          {len(diff_text)} chars")
        
        # Clean the log contents
        print("Cleaning and compressing raw log...")
        cleaned_log = clean_log(raw_log)
        print(f"  Cleaned Log Size:   {len(cleaned_log)} chars (reduced by {100 - (len(cleaned_log)*100//max(1, len(raw_log)))}%)")
        
        # Extract changed files from the diff
        changed_files = extract_changed_files(diff_text)
        print(f"  Changed Files ({len(changed_files)}): {changed_files}")
        
        # Save to SQLite
        repo_identifier = f"{owner}/{repo}"
        
        # Check if record already exists and warn the user
        existing_run = get_run(run_id, repo_identifier, db_path=db_path)
        if existing_run:
            print(f"[WARNING] Run ID {run_id} for repo {repo_identifier} already exists in database (Ingested at: {existing_run['ingested_at']}). Overwriting...")
        
        print(f"Saving structured data to SQLite database ({db_path})...")
        save_run(
            run_id=run_id,
            repo=repo_identifier,
            commit_sha=commit_sha,
            raw_log=raw_log,
            cleaned_log=cleaned_log,
            diff=diff_text,
            changed_files=changed_files,
            status=conclusion,
            db_path=db_path
        )
        print("[SUCCESS] Ingestion completed successfully! Data saved to runs table.")
        
    except Exception as e:
        print(f"\n[ERROR] Ingestion failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()

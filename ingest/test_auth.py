import os
import sys
import json
import zipfile
import io

try:
    from .fetch import load_env, make_request
except ImportError:
    from fetch import load_env, make_request

def test_github_api():
    load_env()
    
    pat = os.getenv('GITHUB_PAT')
    owner = os.getenv('GITHUB_OWNER')
    repos_str = os.getenv('GITHUB_REPOS')
    
    if not pat or pat == 'your_personal_access_token_here':
        print("\n[ERROR] GITHUB_PAT is not configured in .env or system environment.")
        print("Please copy .env.example to .env and put a valid Personal Access Token (PAT).")
        sys.exit(1)
        
    if not owner:
        print("\n[ERROR] GITHUB_OWNER is not configured.")
        sys.exit(1)
        
    if not repos_str:
        print("\n[ERROR] GITHUB_REPOS is not configured.")
        sys.exit(1)
        
    repos = [r.strip() for r in repos_str.split(',') if r.strip()]
    
    print(f"\nConfiguration:")
    print(f"  Owner: {owner}")
    print(f"  Repos: {repos}")
    print(f"  PAT:   {'*' * 8}{pat[-4:] if len(pat) > 4 else ''}\n")
    
    for repo in repos:
        print(f"Checking access for repository: {owner}/{repo}...")
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs?per_page=3"
        try:
            body_bytes, _ = make_request(url, pat)
            data = json.loads(body_bytes.decode('utf-8'))
            runs = data.get('workflow_runs', [])
            print(f"  Successfully fetched workflow runs! Found {data.get('total_count', 0)} runs.")
            
            if not runs:
                print("  No runs found in this repository. Push a commit/workflow to trigger one.")
                continue
                
            for idx, run in enumerate(runs):
                status = run.get('status')
                conclusion = run.get('conclusion')
                run_id = run.get('id')
                name = run.get('name', 'Workflow')
                event = run.get('event')
                print(f"  [{idx+1}] Run ID: {run_id} | Name: '{name}' | Status: {status} | Conclusion: {conclusion} | Event: {event}")
                
                # Test downloading logs for the first run we find
                if idx == 0:
                    print(f"  Testing log downloading for Run ID {run_id}...")
                    log_url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
                    try:
                        # Log download endpoint returns a redirect to a zip file. urllib follows redirects automatically.
                        log_zip_bytes, headers = make_request(log_url, pat)
                        
                        # Verify we received a zip file
                        with zipfile.ZipFile(io.BytesIO(log_zip_bytes)) as z:
                            file_names = z.namelist()
                            print(f"    Successfully downloaded and parsed logs zip file!")
                            print(f"    Number of files in zip: {len(file_names)}")
                            if file_names:
                                print(f"    Example log file: {file_names[0]}")
                    except Exception as le:
                        print(f"    Failed to retrieve/parse logs: {le}")
            print("-" * 50)
            
        except Exception as e:
            print(f"  Error accessing repo {repo}: {e}")
            print("-" * 50)

if __name__ == '__main__':
    test_github_api()

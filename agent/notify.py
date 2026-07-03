import os
import json
import urllib.error
from ingest.fetch import make_request

def post_github_comment(repo: str, commit_sha: str, result: dict, pat: str = None) -> bool:
    """
    Posts the classification result as a comment on the GitHub commit.
    """
    if not pat:
        pat = os.getenv('GITHUB_PAT')
        
    if not pat or pat == 'your_personal_access_token_here':
        print("[Notify] GITHUB_PAT not set, skipping GitHub comment.")
        return False
        
    if not commit_sha:
        print("[Notify] No commit_sha provided, skipping GitHub comment.")
        return False

    category = result.get('category', 'Unknown')
    confidence = result.get('confidence', 0.0)
    hypothesis = result.get('hypothesis', 'No hypothesis provided.')
    overridden = result.get('overridden', False)

    # Format the markdown comment
    body = f"## 🤖 CI Triage Report\n\n"
    body += f"**Category**: `{category}`\n"
    
    if overridden:
        body += f"**Confidence**: `100%` *(Deterministic Override)*\n\n"
        body += f"**Reason**: {hypothesis}\n"
    else:
        body += f"**Confidence**: `{confidence * 100:.1f}%`\n\n"
        body += f"**Hypothesis**: {hypothesis}\n"
        
    if result.get('initial_category') and result.get('initial_category') != category:
        body += f"\n> *Note: Initial classification was `{result.get('initial_category')}`, but was corrected after fetching extra context.*"

    payload = json.dumps({"body": body}).encode('utf-8')
    url = f"https://api.github.com/repos/{repo}/commits/{commit_sha}/comments"

    print(f"[Notify] Posting comment to {url}...")
    try:
        make_request(url, pat=pat, data=payload, method="POST")
        print(f"[Notify] Successfully posted commit comment!")
        return True
    except urllib.error.HTTPError as e:
        print(f"[Notify] Failed to post comment (HTTP {e.code}: {e.reason})")
        return False
    except Exception as e:
        print(f"[Notify] Failed to post comment: {e}")
        return False

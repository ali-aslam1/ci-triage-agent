import sys
import os
import re

from ingest import load_env, init_db
from agent import classify_run

# Regex pattern to parse github repository owner, name, and run ID from Actions URL
URL_PATTERN = re.compile(r'github\.com/([^/]+)/([^/]+)/actions/runs/(\d+)')

def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    # Load configuration
    load_env()

    db_path = os.getenv("GITHUB_TRIAGE_DB", "triage.db")
    
    # Initialize DB (creates classifications table if not present)
    init_db(db_path)

    if len(sys.argv) < 2:
        print("Usage: python run_classify.py <github_actions_run_url>")
        print("Example: python run_classify.py https://github.com/ali-aslam1/pdf-ai-research-assistant/actions/runs/28305298829")
        sys.exit(1)

    arg = sys.argv[1].strip()
    match = URL_PATTERN.search(arg)

    if not match:
        print(f"[ERROR] Invalid argument: '{arg}'")
        print("Must be a full GitHub Actions Run URL, e.g.:")
        print("  https://github.com/<owner>/<repo>/actions/runs/<run_id>")
        sys.exit(1)

    owner = match.group(1)
    name = match.group(2)
    repo = f"{owner}/{name}"
    run_id = match.group(3)

    print(f"Classifying Run:")
    print(f"  Run ID: {run_id}")
    if repo:
        print(f"  Repo:   {repo}")
    print("Connecting to LLM (Groq Llama 3.3 70B)...")

    try:
        result = classify_run(run_id=run_id, repo=repo, db_path=db_path)
        
        print("\n" + "="*50)
        print("CLASSIFICATION RESULT")
        print("="*50)
        print(f"Category:   {result['category']}")
        print(f"Confidence: {result['confidence']:.2f}")
        if result.get("initial_category"):
            print(f"  (Retried from: {result['initial_category']} with confidence {result['initial_confidence']:.2f})")
        print(f"Hypothesis: {result['hypothesis']}")
        print(f"Overridden: {result.get('overridden', False)}")
        print("Evidence lines:")
        for line in result['evidence_lines']:
            print(f"  - {line}")
        print("="*50)
        print("[SUCCESS] Classification processed and stored in database.")
        
    except Exception as e:
        print(f"\n[ERROR] Classification failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()

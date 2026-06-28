import sys

try:
    from .fetch import fetch_run
except ImportError:
    from fetch import fetch_run

def main():
    # Configure stdout to use UTF-8 on Windows consoles to prevent encoding errors
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        
    # If a run ID is passed via CLI, use it; otherwise use one of the known run IDs
    if len(sys.argv) > 1:
        run_id = sys.argv[1]
    else:
        # Default to a known run ID from the logs we saw
        run_id = "28305298829" # From pdf-ai-research-assistant
        
    print(f"Testing fetch_run with Run ID: {run_id}")
    try:
        res = fetch_run(run_id)
        
        print("\n--- Success! Results Summary ---")
        print(f"Triggering Commit SHA: {res['commit_sha']}")
        
        log_text = res['log_text']
        print(f"Log text length: {len(log_text)} chars")
        if log_text:
            print("\nLog preview (first 500 chars):")
            print(log_text[:500])
            print("...")
            print("\nLog preview (last 500 chars):")
            print(log_text[-500:])
        else:
            print("Log is empty.")
            
        diff_text = res['diff']
        print(f"\nDiff text length: {len(diff_text)} chars")
        if diff_text:
            print("\nDiff preview (first 500 chars):")
            print(diff_text[:500])
            print("...")
        else:
            print("Diff is empty.")
            
    except Exception as e:
        print(f"\n[ERROR] fetch_run failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()

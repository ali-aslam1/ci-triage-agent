import sqlite3
import json
import sys
import os

try:
    from .correlate import correlate_run
except ImportError:
    from correlate import correlate_run

def test_correlation():
    db_path = os.getenv("GITHUB_TRIAGE_DB", "triage.db")
    if not os.path.exists(db_path):
        print(f"[ERROR] Database file '{db_path}' not found. Cannot run verification.")
        sys.exit(1)
        
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Test Run ID 28305298829 (Syntax failure where tests/test_syntax.py is in the log)
    cursor.execute("SELECT cleaned_log, changed_files FROM runs WHERE run_id = '28305298829'")
    row_syntax = cursor.fetchone()
    if not row_syntax:
        print("[ERROR] Seed run 28305298829 not found in DB.")
        sys.exit(1)
        
    log_syntax = row_syntax["cleaned_log"]
    changed_syntax = json.loads(row_syntax["changed_files"])
    
    res_syntax = correlate_run(log_syntax, changed_syntax)
    print("="*40)
    print("TEST CASE 1: Syntax Failure (Run 28305298829)")
    print("="*40)
    print(f"Changed files: {changed_syntax}")
    print(f"Matched files: {res_syntax['matched_files']}")
    print(f"any_file_in_diff: {res_syntax['any_file_in_diff']}")
    print(f"Hint: {res_syntax['hint']}")
    
    # Assertions
    assert res_syntax["any_file_in_diff"] is True, "Expected any_file_in_diff to be True for syntax failure."
    assert "tests/test_syntax.py" in res_syntax["matched_files"], "Expected tests/test_syntax.py to be matched."
    print("[SUCCESS] Test Case 1 passed!")
    
    # 2. Test Run ID 28305300755 (Environment setup/pip install failure)
    cursor.execute("SELECT cleaned_log, changed_files FROM runs WHERE run_id = '28305300755'")
    row_env = cursor.fetchone()
    if not row_env:
        print("[ERROR] Seed run 28305300755 not found in DB.")
        sys.exit(1)
        
    log_env = row_env["cleaned_log"]
    changed_env = json.loads(row_env["changed_files"])
    
    res_env = correlate_run(log_env, changed_env)
    print("\n" + "="*40)
    print("TEST CASE 2: Environment Failure (Run 28305300755)")
    print("="*40)
    print(f"Changed files: {changed_env}")
    print(f"Matched files: {res_env['matched_files']}")
    print(f"any_file_in_diff: {res_env['any_file_in_diff']}")
    print(f"Hint: {res_env['hint']}")
    
    # Assertions
    assert res_env["any_file_in_diff"] is False, "Expected any_file_in_diff to be False for environment failure."
    assert len(res_env["matched_files"]) == 0, f"Expected matched_files to be empty, got: {res_env['matched_files']}"
    print("[SUCCESS] Test Case 2 passed!")
    
    conn.close()
    print("\n[ALL TESTS PASSED SUCCESSFULLY]")

if __name__ == "__main__":
    test_correlation()

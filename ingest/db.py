import sqlite3
import json
import datetime
from typing import Optional, Dict, List

def init_db(db_path: str = "triage.db"):
    """
    Initializes the SQLite database and creates the runs table if it doesn't exist.
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT,
                repo TEXT,
                commit_sha TEXT,
                raw_log TEXT,
                cleaned_log TEXT,
                diff TEXT,
                changed_files TEXT,
                status TEXT,
                ingested_at TIMESTAMP,
                PRIMARY KEY (run_id, repo)
            )
        """)
        conn.commit()
    finally:
        conn.close()

def save_run(
    run_id: str,
    repo: str,
    commit_sha: str,
    raw_log: str,
    cleaned_log: str,
    diff: str,
    changed_files,  # list/set/tuple or JSON string
    status: str,
    db_path: str = "triage.db"
):
    """
    Saves or replaces a workflow run row inside the SQLite runs table.
    """
    # Serialize list/tuple to a JSON string if it isn't already a string
    if not isinstance(changed_files, str):
        changed_files_str = json.dumps(list(changed_files))
    else:
        changed_files_str = changed_files

    ingested_at_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO runs (
                run_id, repo, commit_sha, raw_log, cleaned_log, diff, changed_files, status, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(run_id),
            repo,
            commit_sha,
            raw_log,
            cleaned_log,
            diff,
            changed_files_str,
            status,
            ingested_at_str
        ))
        conn.commit()
    finally:
        conn.close()

def get_run(run_id: str, repo: str, db_path: str = "triage.db") -> Optional[Dict]:
    """
    Retrieves a run by run_id and repo.
    Returns a dictionary of column names to values, or None if not found.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT run_id, repo, commit_sha, raw_log, cleaned_log, diff, changed_files, status, ingested_at FROM runs WHERE run_id = ? AND repo = ?",
            (str(run_id), repo)
        )
        row = cursor.fetchone()
        if row:
            res = dict(row)
            # Deserialize changed_files back into a list if possible
            if res.get("changed_files"):
                try:
                    res["changed_files"] = json.loads(res["changed_files"])
                except Exception:
                    pass
            return res
        return None
    finally:
        conn.close()

def list_runs(db_path: str = "triage.db") -> List[Dict]:
    """
    Lists all workflow runs currently saved in the runs table.
    Returns a list of dictionaries.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT run_id, repo, commit_sha, status, changed_files, ingested_at FROM runs ORDER BY ingested_at DESC"
        )
        rows = cursor.fetchall()
        runs = []
        for row in rows:
            res = dict(row)
            if res.get("changed_files"):
                try:
                    res["changed_files"] = json.loads(res["changed_files"])
                except Exception:
                    pass
            runs.append(res)
        return runs
    finally:
        conn.close()

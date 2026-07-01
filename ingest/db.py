import sqlite3
import json
import datetime
from typing import Optional, Dict, List

def init_db(db_path: str = "triage.db"):
    """
    Initializes the SQLite database and creates all required tables if they don't exist.
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS classifications (
                run_id TEXT,
                repo TEXT,
                category TEXT,
                confidence REAL,
                hypothesis TEXT,
                evidence TEXT,
                overridden INTEGER DEFAULT 0,
                initial_category TEXT,
                initial_confidence REAL,
                classified_at TIMESTAMP,
                PRIMARY KEY (run_id, repo),
                FOREIGN KEY (run_id, repo) REFERENCES runs (run_id, repo) ON DELETE CASCADE
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

def save_classification(
    run_id: str,
    repo: str,
    category: str,
    confidence: float,
    hypothesis: str,
    evidence,  # list/set/tuple or JSON string
    overridden: bool = False,
    initial_category: Optional[str] = None,
    initial_confidence: Optional[float] = None,
    db_path: str = "triage.db"
):
    """
    Saves or replaces a classification record inside the SQLite classifications table.
    """
    if not isinstance(evidence, str):
        evidence_str = json.dumps(list(evidence))
    else:
        evidence_str = evidence

    classified_at_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO classifications (
                run_id, repo, category, confidence, hypothesis, evidence, overridden,
                initial_category, initial_confidence, classified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(run_id),
            repo,
            category,
            float(confidence),
            hypothesis,
            evidence_str,
            1 if overridden else 0,
            initial_category,
            initial_confidence if initial_confidence is None else float(initial_confidence),
            classified_at_str
        ))
        conn.commit()
    finally:
        conn.close()

def get_classification(run_id: str, repo: str, db_path: str = "triage.db") -> Optional[Dict]:
    """
    Retrieves a classification by run_id and repo.
    Returns a dictionary of column names to values, or None if not found.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT run_id, repo, category, confidence, hypothesis, evidence, overridden,
                   initial_category, initial_confidence, classified_at
            FROM classifications
            WHERE run_id = ? AND repo = ?
        """, (str(run_id), repo))
        row = cursor.fetchone()
        if row:
            res = dict(row)
            if res.get("evidence"):
                try:
                    res["evidence"] = json.loads(res["evidence"])
                except Exception:
                    pass
            if "overridden" in res:
                res["overridden"] = bool(res["overridden"])
            return res
        return None
    finally:
        conn.close()

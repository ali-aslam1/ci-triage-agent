import json
from unittest.mock import patch

try:
    from .flaky import check_flaky_override
except ImportError:
    from flaky import check_flaky_override

def test_flaky_override_same_sha():
    """
    Test that flaky override fires when adjacent run is successful and has the exact same SHA.
    """
    current_run_json = {
        "workflow_id": 999,
        "run_number": 5,
        "head_sha": "same-sha-123",
        "conclusion": "failure"
    }
    
    workflow_runs_json = {
        "workflow_runs": [
            {
                "id": 1001,
                "run_number": 4,
                "conclusion": "success",
                "head_sha": "same-sha-123"
            }
        ]
    }
    
    # Mock make_request to return responses
    def mock_make_request(url, pat, accept=None):
        if "actions/runs/123" in url:
            return json.dumps(current_run_json).encode("utf-8"), None
        elif "workflows/999/runs" in url:
            return json.dumps(workflow_runs_json).encode("utf-8"), None
        raise ValueError(f"Unexpected API call in mock: {url}")
        
    with patch("agent.flaky.make_request", side_effect=mock_make_request), \
         patch("agent.flaky.os.getenv", return_value="mock_pat"):
        result = check_flaky_override(run_id="123", repo="owner/repo")
        assert result is True, "Expected same SHA adjacent run to trigger flaky override"
        print("[SUCCESS] test_flaky_override_same_sha passed!")

def test_flaky_override_no_repo_changes():
    """
    Test that flaky override fires when adjacent run is successful and only non-code files changed.
    """
    current_run_json = {
        "workflow_id": 999,
        "run_number": 5,
        "head_sha": "new-sha",
        "conclusion": "failure"
    }
    
    workflow_runs_json = {
        "workflow_runs": [
            {
                "id": 1001,
                "run_number": 4,
                "conclusion": "success",
                "head_sha": "old-sha"
            }
        ]
    }
    
    mock_diff = (
        "diff --git a/README.md b/README.md\n"
        "index e69de29..d2d0b64 100644\n"
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -0,0 +1 @@\n"
        "+# Some update to readme\n"
    )
    
    def mock_make_request(url, pat, accept=None):
        if "actions/runs/123" in url:
            return json.dumps(current_run_json).encode("utf-8"), None
        elif "workflows/999/runs" in url:
            return json.dumps(workflow_runs_json).encode("utf-8"), None
        elif "compare/old-sha...new-sha" in url:
            # We sorted chronologically: older run (run 4) SHA is "old-sha", newer (run 5) SHA is "new-sha"
            return mock_diff.encode("utf-8"), None
        raise ValueError(f"Unexpected API call in mock: {url}")
        
    with patch("agent.flaky.make_request", side_effect=mock_make_request), \
         patch("agent.flaky.os.getenv", return_value="mock_pat"):
        result = check_flaky_override(run_id="123", repo="owner/repo")
        assert result is True, "Expected non-code changes to trigger flaky override"
        print("[SUCCESS] test_flaky_override_no_repo_changes passed!")

def test_flaky_override_with_repo_changes():
    """
    Test that flaky override DOES NOT fire when adjacent run is successful but code files changed.
    """
    current_run_json = {
        "workflow_id": 999,
        "run_number": 5,
        "head_sha": "new-sha",
        "conclusion": "failure"
    }
    
    workflow_runs_json = {
        "workflow_runs": [
            {
                "id": 1001,
                "run_number": 4,
                "conclusion": "success",
                "head_sha": "old-sha"
            }
        ]
    }
    
    mock_diff = (
        "diff --git a/app.py b/app.py\n"
        "index e69de29..d2d0b64 100644\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -0,0 +1 @@\n"
        "+def new_function(): pass\n"
    )
    
    def mock_make_request(url, pat, accept=None):
        if "actions/runs/123" in url:
            return json.dumps(current_run_json).encode("utf-8"), None
        elif "workflows/999/runs" in url:
            return json.dumps(workflow_runs_json).encode("utf-8"), None
        elif "compare/old-sha...new-sha" in url:
            return mock_diff.encode("utf-8"), None
        raise ValueError(f"Unexpected API call in mock: {url}")
        
    with patch("agent.flaky.make_request", side_effect=mock_make_request), \
         patch("agent.flaky.os.getenv", return_value="mock_pat"):
        result = check_flaky_override(run_id="123", repo="owner/repo")
        assert result is False, "Expected code changes to block flaky override"
        print("[SUCCESS] test_flaky_override_with_repo_changes passed!")

if __name__ == "__main__":
    test_flaky_override_same_sha()
    test_flaky_override_no_repo_changes()
    test_flaky_override_with_repo_changes()
    print("\n[ALL FLAKY TESTS PASSED SUCCESSFULLY]")

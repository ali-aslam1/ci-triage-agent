from unittest.mock import patch, MagicMock

try:
    from .classify import _needs_retry, classify_run
except ImportError:
    from classify import _needs_retry, classify_run

def test_needs_retry_low_confidence():
    """
    Test that low confidence (< 0.6) triggers a retry.
    """
    result = {
        "category": "Regression",
        "confidence": 0.5,
        "hypothesis": "Failing test due to assertion error",
        "evidence_lines": ["AssertionError: assert 1 == 2"]
    }
    assert _needs_retry(result) is True, "Expected low confidence to trigger retry"
    print("[SUCCESS] test_needs_retry_low_confidence passed!")

def test_needs_retry_contradiction():
    """
    Test that a keyword contradiction triggers a retry.
    """
    # Category is Flaky, but evidence contains "SyntaxError" (expected Lint/Syntax)
    result_syntax = {
        "category": "Flaky",
        "confidence": 0.8,
        "hypothesis": "Intermittent failure",
        "evidence_lines": ["SyntaxError: expected ':'"]
    }
    assert _needs_retry(result_syntax) is True, "Expected SyntaxError contradiction to trigger retry"

    # Category is Regression, but evidence contains "ModuleNotFoundError" (expected Environment)
    result_env = {
        "category": "Regression",
        "confidence": 0.7,
        "hypothesis": "Assertion failure",
        "evidence_lines": ["ModuleNotFoundError: No module named 'groq'"]
    }
    assert _needs_retry(result_env) is True, "Expected ModuleNotFoundError contradiction to trigger retry"
    print("[SUCCESS] test_needs_retry_contradiction passed!")

def test_needs_retry_no_trigger():
    """
    Test that high confidence and clean evidence do not trigger a retry.
    """
    result = {
        "category": "Regression",
        "confidence": 0.85,
        "hypothesis": "Broken logic",
        "evidence_lines": ["AssertionError: assert 4 == 5"]
    }
    assert _needs_retry(result) is False, "Expected normal high confidence run to not trigger retry"
    print("[SUCCESS] test_needs_retry_no_trigger passed!")

def test_classify_run_retry_loop_success():
    """
    Test the full classify_run retry flow:
    - Initial LLM classification triggers a retry (due to contradiction).
    - Second LLM classification is accepted (high confidence, clean).
    - Database is populated with initial_category/initial_confidence.
    """
    mock_run = {
        "run_id": "999",
        "repo": "owner/repo",
        "commit_sha": "sha123",
        "cleaned_log": "log text containing SyntaxError",
        "changed_files": []
    }

    # Initial response has a contradiction (Flaky but contains SyntaxError)
    initial_llm_response = {
        "category": "Flaky",
        "confidence": 0.8,
        "hypothesis": "Flaky error",
        "evidence_lines": ["SyntaxError: expected ':'"]
    }

    # Final response is correct (Lint/Syntax, high confidence)
    final_llm_response = {
        "category": "Lint/Syntax",
        "confidence": 0.9,
        "hypothesis": "Syntax error in file",
        "evidence_lines": ["SyntaxError: expected ':'"]
    }

    # Mock DB functions, log correlation, flaky override checks, and LLM calls
    mock_get_run = MagicMock(return_value=mock_run)
    mock_correlate = MagicMock(return_value={"hint": "", "matched_files": [], "any_file_in_diff": False})
    mock_flaky = MagicMock(return_value=False)
    
    # We call classify_log twice: first returns initial_llm_response, second returns final_llm_response
    mock_classify_log = MagicMock(side_effect=[initial_llm_response, final_llm_response])
    mock_fetch_context = MagicMock(return_value="CONTEXT: code here")
    mock_save_classification = MagicMock()

    with patch("ingest.get_run", mock_get_run), \
         patch("agent.correlate.correlate_run", mock_correlate), \
         patch("agent.flaky.check_flaky_override", mock_flaky), \
         patch("agent.classify.classify_log", mock_classify_log), \
         patch("agent.context_fetch.fetch_context_for_run", mock_fetch_context), \
         patch("ingest.save_classification", mock_save_classification):
        
        result = classify_run("999", "owner/repo", db_path="dummy.db")

        # Verify retry checks and LLM calls
        assert mock_classify_log.call_count == 2, "Expected LLM to be called twice (initial + 1 retry)"
        assert mock_fetch_context.call_count == 1, "Expected context-fetch to be called exactly once"
        
        # Verify result contains final classification
        assert result["category"] == "Lint/Syntax"
        assert result["confidence"] == 0.9
        
        # Verify initial details were recorded
        assert result["initial_category"] == "Flaky"
        assert result["initial_confidence"] == 0.8

        # Verify save_classification was called with initial fields
        mock_save_classification.assert_called_once_with(
            run_id="999",
            repo="owner/repo",
            category="Lint/Syntax",
            confidence=0.9,
            hypothesis="Syntax error in file",
            evidence=["SyntaxError: expected ':'"],
            overridden=False,
            initial_category="Flaky",
            initial_confidence=0.8,
            db_path="dummy.db"
        )
        print("[SUCCESS] test_classify_run_retry_loop_success passed!")

if __name__ == "__main__":
    test_needs_retry_low_confidence()
    test_needs_retry_contradiction()
    test_needs_retry_no_trigger()
    test_classify_run_retry_loop_success()
    print("\n[ALL RETRY & CONTRADICTION TESTS PASSED SUCCESSFULLY]")

import json
import base64
from unittest.mock import patch

try:
    from .context_fetch import parse_stack_trace, fetch_function_source, fetch_context_for_run
except ImportError:
    from context_fetch import parse_stack_trace, fetch_function_source, fetch_context_for_run

def test_parse_stack_trace_syntax_error():
    """
    Test parsing pytest collection phase SyntaxError log structure.
    """
    log_text = (
        "/opt/hostedtoolcache/Python/3.10.20/x64/lib/python3.10/site-packages/_pytest/assertion/rewrite.py:348: in _rewrite_test\n"
        "    tree = ast.parse(source, filename=strfn)\n"
        "E     File \"/home/runner/work/pdf-ai-research-assistant/pdf-ai-research-assistant/tests/test_syntax.py\", line 2\n"
        "E       def test_syntax_error()\n"
        "E                              ^\n"
        "E   SyntaxError: expected ':'\n"
    )
    evidence_lines = [
        "E     File \"/home/runner/work/pdf-ai-research-assistant/pdf-ai-research-assistant/tests/test_syntax.py\", line 2",
        "E       def test_syntax_error()",
        "E   SyntaxError: expected ':'"
    ]
    
    res = parse_stack_trace(log_text, evidence_lines)
    assert res is not None
    assert res["file_path"] == "tests/test_syntax.py"
    assert res["function_name"] == "test_syntax_error"
    print("[SUCCESS] test_parse_stack_trace_syntax_error passed!")

def test_parse_stack_trace_standard_traceback():
    """
    Test parsing standard python traceback (e.g. File ..., line ..., in func).
    """
    log_text = (
        "Traceback (most recent call last):\n"
        "  File \"tests/test_regression.py\", line 3, in test_addition\n"
        "    assert 2 + 2 == 5\n"
        "AssertionError\n"
    )
    evidence = [
        "  File \"tests/test_regression.py\", line 3, in test_addition",
        "AssertionError"
    ]
    
    res = parse_stack_trace(log_text, evidence)
    assert res is not None
    assert res["file_path"] == "tests/test_regression.py"
    assert res["function_name"] == "test_addition"
    print("[SUCCESS] test_parse_stack_trace_standard_traceback passed!")

def test_parse_stack_trace_failed_line():
    """
    Test parsing pytest FAILED lines.
    """
    log_text = "=========================== FAILURES ===========================\n"
    evidence = [
        "FAILED tests/test_regression.py::test_addition - AssertionError"
    ]
    
    res = parse_stack_trace(log_text, evidence)
    assert res is not None
    assert res["file_path"] == "tests/test_regression.py"
    assert res["function_name"] == "test_addition"
    print("[SUCCESS] test_parse_stack_trace_failed_line passed!")

def test_fetch_function_source_ast():
    """
    Test extracting function source with AST parsing strategy.
    """
    file_content = (
        "def foo():\n"
        "    return 'foo'\n"
        "\n"
        "def bar():\n"
        "    # Target function\n"
        "    a = 1\n"
        "    b = 2\n"
        "    return a + b\n"
        "\n"
        "def baz():\n"
        "    pass\n"
    )
    
    # Mock make_request to return content
    mock_api_data = {
        "content": base64.b64encode(file_content.encode("utf-8")).decode("utf-8")
    }
    
    with patch("agent.context_fetch.make_request", return_value=(json.dumps(mock_api_data).encode("utf-8"), None)):
        source = fetch_function_source("owner/repo", "sha123", "app.py", "bar", "pat123")
        assert "def bar():" in source
        assert "return a + b" in source
        assert "def foo():" not in source
        assert "def baz():" not in source
        print("[SUCCESS] test_fetch_function_source_ast passed!")

def test_fetch_function_source_string_search_fallback():
    """
    Test string search fallback strategy when file has syntax errors.
    """
    broken_file_content = (
        "def foo():\n"
        "    return 'foo'\n"
        "\n"
        "# Missing colon here raises SyntaxError in AST parse\n"
        "def bar()\n"
        "    a = 1\n"
        "    b = 2\n"
        "    return a + b\n"
    )
    
    mock_api_data = {
        "content": base64.b64encode(broken_file_content.encode("utf-8")).decode("utf-8")
    }
    
    with patch("agent.context_fetch.make_request", return_value=(json.dumps(mock_api_data).encode("utf-8"), None)):
        source = fetch_function_source("owner/repo", "sha123", "app.py", "bar", "pat123")
        assert "def bar()" in source
        assert "return a + b" in source
        assert "def foo():" not in source
        print("[SUCCESS] test_fetch_function_source_string_search_fallback passed!")

def test_fetch_function_source_general_fallback_no_function():
    """
    Test fallback to returning top of the file when no function name is given.
    """
    file_content = "\n".join([f"line_{i}" for i in range(150)])
    mock_api_data = {
        "content": base64.b64encode(file_content.encode("utf-8")).decode("utf-8")
    }

    with patch("agent.context_fetch.make_request", return_value=(json.dumps(mock_api_data).encode("utf-8"), None)):
        source = fetch_function_source("owner/repo", "sha123", "app.py", None, "pat123")
        assert source.splitlines()[-1] == "line_99", "Expected exactly first 100 lines (0 to 99)"
        print("[SUCCESS] test_fetch_function_source_general_fallback_no_function passed!")

def test_fetch_function_source_general_fallback_not_found():
    """
    Test fallback to returning top of the file when function is not found in source.
    """
    file_content = "\n".join([f"line_{i}" for i in range(150)])
    mock_api_data = {
        "content": base64.b64encode(file_content.encode("utf-8")).decode("utf-8")
    }

    with patch("agent.context_fetch.make_request", return_value=(json.dumps(mock_api_data).encode("utf-8"), None)):
        source = fetch_function_source("owner/repo", "sha123", "app.py", "missing_func", "pat123")
        assert source.splitlines()[-1] == "line_99", "Expected exactly first 100 lines (0 to 99)"
        print("[SUCCESS] test_fetch_function_source_general_fallback_not_found passed!")

def test_fetch_context_for_run_end_to_end():
    """
    End-to-end test: parse_stack_trace + fetch_function_source + header formatting.
    """
    log_text = (
        "Traceback (most recent call last):\n"
        "  File \"tests/test_regression.py\", line 3, in test_addition\n"
        "    assert 2 + 2 == 5\n"
        "AssertionError\n"
    )
    evidence_lines = [
        "  File \"tests/test_regression.py\", line 3, in test_addition",
        "AssertionError"
    ]
    file_content = (
        "def test_addition():\n"
        "    assert 2 + 2 == 5\n"
    )
    mock_api_data = {
        "content": base64.b64encode(file_content.encode("utf-8")).decode("utf-8")
    }

    with patch("agent.context_fetch.make_request", return_value=(json.dumps(mock_api_data).encode("utf-8"), None)), \
         patch("agent.context_fetch.os.getenv", return_value="mock_pat"):
        result = fetch_context_for_run(log_text, evidence_lines, "owner/repo", "sha123")
        assert result is not None, "Expected a non-None context result"
        assert result.startswith("CONTEXT — tests/test_regression.py :: test_addition")
        assert "def test_addition():" in result
        print("[SUCCESS] test_fetch_context_for_run_end_to_end passed!")

if __name__ == "__main__":
    test_parse_stack_trace_syntax_error()
    test_parse_stack_trace_standard_traceback()
    test_parse_stack_trace_failed_line()
    test_fetch_function_source_ast()
    test_fetch_function_source_string_search_fallback()
    test_fetch_function_source_general_fallback_no_function()
    test_fetch_function_source_general_fallback_not_found()
    test_fetch_context_for_run_end_to_end()
    print("\n[ALL CONTEXT FETCH TESTS PASSED SUCCESSFULLY]")

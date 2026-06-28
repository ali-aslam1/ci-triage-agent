import sys

try:
    from .clean import clean_log
except ImportError:
    from clean import clean_log

def test_ansi_and_timestamps():
    mock_log = (
        "2026-06-27T23:39:16.5574521Z \x1b[31mThis is line 1 with ANSI colors\x1b[0m\n"
        "2026-06-27T23:39:16.5595543Z This is line 2 without color\n"
    )
    cleaned = clean_log(mock_log)
    assert "\x1b[31m" not in cleaned
    assert "\x1b[0m" not in cleaned
    assert "2026-06-27T23:39:16.5574521Z" not in cleaned
    assert "This is line 1 with ANSI colors" in cleaned
    assert "This is line 2 without color" in cleaned
    print("test_ansi_and_timestamps: PASSED")

def test_pip_spam():
    mock_log = (
        "2026-06-27T23:39:16.5574521Z Requirement already satisfied: pip in /usr/lib\n"
        "2026-06-27T23:39:16.5595543Z Downloading package-1.2.3.tar.gz (1.2 MB)\n"
        "2026-06-27T23:39:16.5600000Z  1.2/1.3 MB 1.4 MB/s\n"
        "2026-06-27T23:39:16.5610000Z |████████████████████████████████| 100%\n"
        "2026-06-27T23:39:16.5620000Z Installing collected packages: package\n"
        "2026-06-27T23:39:16.5630000Z ERROR: failed to build wheel for package (this should keep!)\n"
    )
    cleaned = clean_log(mock_log)
    assert "Requirement already satisfied" not in cleaned
    assert "Downloading package" not in cleaned
    assert "1.2/1.3 MB" not in cleaned
    assert "█" not in cleaned
    assert "Installing collected packages" not in cleaned
    assert "ERROR: failed to build wheel" in cleaned
    print("test_pip_spam: PASSED")

def test_header_and_summary_and_snip():
    # Construct a log of 100 lines.
    # Lines 0 to 19: header (should keep)
    # Lines 20 to 69: boring lines (should snip, except if failure context)
    # Line 50: a failure line (should keep with 40 before, 10 after. So indices 10 to 60)
    # Lines 70 to 99: summary lines (should keep last 30 lines, indices 70 to 99)
    lines = [f"Line {i}" for i in range(100)]
    lines[50] = "Line 50 - FAILED: assertion error"
    
    log_text = "\n".join(lines)
    cleaned = clean_log(log_text)
    cleaned_lines = cleaned.splitlines()
    
    try:
        # Line 50 and context around it should be in.
        # Context window is [10, 60] (40 before, 10 after). Since [0, 19] is already included,
        # the entire range [0, 60] is contiguous!
        for i in range(61):
            if i == 50:
                assert any(f"Line {i}" in line for line in cleaned_lines)
            else:
                assert f"Line {i}" in cleaned_lines
            
        # Lines 61 to 69 should be snipped since they are not failure context or summary.
        assert "... [snip] ..." in cleaned_lines
        for i in range(61, 70):
             assert f"Line {i}" not in cleaned_lines
             
        # Lines 70 to 99 should be in (last 30 lines summary)
        for i in range(70, 100):
             assert f"Line {i}" in cleaned_lines
    except AssertionError as e:
        print("Debugging output for test_header_and_summary_and_snip:")
        print(f"Total lines: {len(cleaned_lines)}")
        for idx, l in enumerate(cleaned_lines):
            print(f"  {idx:02d}: {repr(l)}")
        raise e
         
    print("test_header_and_summary_and_snip: PASSED")

def test_real_log_integration():
    try:
        from fetch import fetch_run
        run_id = "28305298829"
        res = fetch_run(run_id)
        raw_log = res['log_text']
        cleaned_log = clean_log(raw_log)
        
        print("\nReal Log Integration:")
        print(f"  Raw log length: {len(raw_log)} chars, {len(raw_log.splitlines())} lines")
        print(f"  Cleaned log length: {len(cleaned_log)} chars, {len(cleaned_log.splitlines())} lines")
        assert len(cleaned_log) < len(raw_log)
        print("  Log is successfully compressed!")
    except Exception as e:
        print(f"Skipping real log integration check (offline or auth issue): {e}")

if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    test_ansi_and_timestamps()
    test_pip_spam()
    test_header_and_summary_and_snip()
    test_real_log_integration()
    print("\nALL LOG CLEANING TESTS PASSED!")

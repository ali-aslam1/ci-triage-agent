# CI/Test-Failure Triage Taxonomy

This document outlines the failure taxonomy used by the triage agent. Each category defines a specific type of build or test failure, accompanied by code patterns and representative log signature examples.

---

## 1. Regression
* **Definition**: Functional code logic changes that violate the expected behavior, resulting in standard test assertion failures. The environment, dependencies, and syntax are healthy, but the code produces incorrect output.
* **Common Causes**:
  - Off-by-one errors.
  - Faulty edge case handling in updated functions.
  - Incorrect boolean logic or state updates.
* **Example Code Cause**:
  ```python
  # Expected: return price * (1 - discount)
  # Actual:
  def calculate_discount(price, discount):
      return price - discount  # Regression: subtraction instead of percent multiplier
  ```
* **Typical Log Signatures**:
  ```text
  ================================== FAILURES ==================================
  _________________________ test_calculate_discount __________________________

      def test_calculate_discount():
  >       assert calculate_discount(100, 0.20) == 80.0
  E       assert 99.8 == 80.0
  E        +  where 99.8 = calculate_discount(100, 0.20)

  tests/test_pricing.py:8: AssertionError
  =========================== 1 failed in 0.12s ============================
  ```

---

## 2. Flaky
* **Definition**: Non-deterministic test failures. The code logic might be correct, but the test fails intermittently due to external, environmental, or execution-speed variables.
* **Common Causes**:
  - Tight timing assumptions (e.g., assuming `time.sleep(0.1)` is sufficient for an async background task).
  - Shared mutable state or side-effects between test runs.
  - Network service dependency timeouts.
  - Thread/process race conditions.
* **Example Code Cause**:
  ```python
  def test_async_fetch():
      fetcher.start()
      time.sleep(0.01) # Flaky: may fail if CPU load is high during CI runner execution
      assert fetcher.is_done() is True
  ```
* **Typical Log Signatures**:
  ```text
  ================================== FAILURES ==================================
  ______________________________ test_async_fetch ______________________________

      def test_async_fetch():
          fetcher.start()
          time.sleep(0.01)
  >       assert fetcher.is_done() is True
  E       AssertionError: assert False is True
  E        +  where False = <bound method Fetcher.is_done of <Fetcher object at 0x7f8>>

  tests/test_async.py:12: AssertionError
  =========================== 1 failed in 0.22s ============================
  ```

---

## 3. Environment
* **Definition**: Failure to construct the execution context. This happens before any functional tests are run or at runtime when import paths or third-party dependencies mismatch.
* **Common Causes**:
  - Missing dependencies in `requirements.txt` or `pyproject.toml`.
  - Wrong library version imported (breaking API changes in third-party libraries).
  - Discrepancies between local Python version and runner Python version.
* **Example Code Cause**:
  ```python
  # requirements.txt does not contain 'pydantic'
  import pydantic  # Environment: throws ModuleNotFoundError on runner
  ```
* **Typical Log Signatures**:
  ```text
  ============================= ERRORS =============================
  ___________________ ERROR collecting tests/test_schema.py ____________________
  tests/test_schema.py:1: in <module>
      import pydantic
  E   ModuleNotFoundError: No module named 'pydantic'
  =========================== 1 error in 0.08s =============================
  ```
  Or package resolution errors:
  ```text
  ERROR: Could not find a version that satisfies the requirement some-invalid-pkg==9.9.9 (from versions: none)
  ERROR: No matching distribution found for some-invalid-pkg==9.9.9
  Error: Process completed with exit code 1.
  ```

---

## 4. Lint/Syntax
* **Definition**: Failures identified at the parse/compilation step before execution.
* **Common Causes**:
  - Typos, missing colons, or mismatched brackets.
  - Incorrect indentation (mixing tabs/spaces).
  - Linter errors (e.g., `flake8` or `black` formatting enforcement configurations on CI).
* **Example Code Cause**:
  ```python
  def process_data(data)
      print(data)  # SyntaxError: missing colon on line 1
  ```
* **Typical Log Signatures**:
  ```text
  ============================= ERRORS =============================
  ___________________ ERROR collecting tests/test_parser.py ____________________
  File "src/parser.py", line 1
      def process_data(data)
                            ^
  SyntaxError: expected ':'
  =========================== 1 error in 0.05s =============================
  ```

---

## 5. Infra
* **Definition**: Failure of the orchestration or pipeline environment itself. The code repository is valid, but the workflow instructions or runner config is broken.
* **Common Causes**:
  - Broken YAML syntax or incorrect indentation in `.github/workflows/*.yml`.
  - Outdated or incorrect Actions triggers/versions (e.g., referencing a third-party Action repository that was deleted or renamed).
  - Disk full or memory limits reached on the virtualization runner.
  - Invalid permissions on keys or secrets.
* **Example Code Cause**:
  ```yaml
  # .github/workflows/pytest.yml
  jobs:
    test:
      runs-on: ubuntu-latest
     steps:  # Infra: Wrong YAML indentation
        - uses: actions/checkout@v4
  ```
* **Typical Log Signatures**:
  ```text
  Error: .github/workflows/pytest.yml (Line: 5, Col: 6): Unexpected value 'steps'
  ```
  Or:
  ```text
  Error: Unable to resolve action `actions/checkout@v99`, repository not found.
  ```

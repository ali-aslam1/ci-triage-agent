import os
import json
from typing import Optional

from groq import Groq
from json_repair import repair_json

# ---------------------------------------------------------------------------
# Taxonomy loaded verbatim from taxonomy.md, stripped to plain text for the
# system prompt. Defined as a module-level constant so it is only built once.
# ---------------------------------------------------------------------------
TAXONOMY_TEXT = """
FAILURE TAXONOMY — use exactly these five category names:

1. Regression
   Definition: Functional code logic changes that violate the expected behavior,
   resulting in standard test assertion failures. The environment, dependencies,
   and syntax are healthy, but the code produces incorrect output.
   Common causes: off-by-one errors, faulty edge case handling, incorrect boolean
   logic or state updates.
   Typical log signatures: AssertionError with assert X == Y lines, FAILED banner,
   test_*.py assertion failures.

2. Flaky
   Definition: Non-deterministic test failures. The code logic might be correct,
   but the test fails intermittently due to external, environmental, or
   execution-speed variables.
   Common causes: tight timing assumptions (time.sleep), shared mutable state,
   network service dependency timeouts, thread/process race conditions.
   Typical log signatures: AssertionError on timing or async checks, same test
   passes on re-run, no changed source files referenced in the traceback.

3. Environment
   Definition: Failure to construct the execution context. Happens before any
   functional tests are run, or at runtime when import paths or third-party
   dependencies mismatch.
   Common causes: missing packages in requirements.txt or pyproject.toml, wrong
   library version (breaking API changes), Python version mismatch between local
   and CI runner.
   Typical log signatures: ModuleNotFoundError, ImportError, pip ERROR: Could not
   find a version that satisfies the requirement, ERROR: No matching distribution.

4. Lint/Syntax
   Definition: Failures identified at the parse/compilation step before execution.
   Common causes: typos, missing colons, mismatched brackets, mixed tabs/spaces,
   linter enforcement (flake8, black).
   Typical log signatures: SyntaxError, IndentationError, ERROR collecting
   tests/test_*.py during collection phase, flake8/black diff output.

5. Infra
   Definition: Failure of the orchestration or pipeline environment itself. The
   code repository is valid, but the workflow instructions or runner config is
   broken.
   Common causes: broken YAML syntax in .github/workflows/*.yml, outdated or
   missing Actions versions, disk full / memory limits, invalid secret permissions.
   Typical log signatures: "Unexpected value 'steps'", "Unable to resolve action",
   "Out of disk space", secret-related permission errors.
"""

SYSTEM_PROMPT = f"""You are a CI/CD failure triage expert. Your task is to classify
a GitHub Actions workflow failure into exactly one category from the taxonomy below,
then produce a structured JSON response.

{TAXONOMY_TEXT}

CORRELATION HINT: You will receive a hint produced by deterministic code analysis
that tells you whether any of the files changed in this commit appear in the failure
log. Use this as a strong signal but not an absolute rule:
- If matched files are found in the log → strongly consider Regression or Lint/Syntax.
- If NO matched files are found in the log → strongly consider Flaky or Environment.

OUTPUT RULES — you MUST respond with ONLY a JSON object, no prose before or after:
{{
  "category": "<one of: Regression | Flaky | Environment | Lint/Syntax | Infra>",
  "confidence": <float between 0.0 and 1.0>,
  "hypothesis": "<one concise sentence explaining the root cause>",
  "evidence_lines": ["<key log line 1>", "<key log line 2>", ...]
}}

evidence_lines must be verbatim excerpts from the log, maximum 5 items.
Do not wrap the JSON in markdown code fences.
"""

MODEL = "llama-3.3-70b-versatile"


def _load_groq_key() -> str:
    """Reads GROQ_API_KEY from environment, raising clearly if missing."""
    key = os.getenv("GROQ_API_KEY")
    if not key or key == "your_groq_api_key_here":
        raise ValueError(
            "GROQ_API_KEY is not configured. "
            "Add it to your .env file (see .env.example)."
        )
    return key


def _build_user_message(cleaned_log: str, correlation: dict, extra_context: Optional[str] = None) -> str:
    """Formats the user turn combining the log, correlation hint, and optional context."""
    hint = correlation.get("hint", "")
    matched = correlation.get("matched_files", [])
    any_match = correlation.get("any_file_in_diff", False)

    matched_str = ", ".join(matched) if matched else "none"
    user_msg = (
        f"CORRELATION ANALYSIS:\n"
        f"  any_file_in_diff : {any_match}\n"
        f"  matched_files    : {matched_str}\n"
        f"  hint             : {hint}\n\n"
    )
    if extra_context:
        user_msg += (
            f"ADDITIONAL CONTEXT — source code of the function from the stack trace:\n"
            f"{extra_context}\n\n"
        )
    user_msg += (
        f"FAILURE LOG:\n"
        f"{cleaned_log}"
    )
    return user_msg


def _parse_response(raw_text: str) -> dict:
    """
    Parses the LLM response into a validated dict.
    Falls back to json_repair if the raw text is not valid JSON.
    """
    raw_text = raw_text.strip()

    # Try direct parse first
    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        # Apply json_repair as fallback
        repaired = repair_json(raw_text, return_objects=True)
        if isinstance(repaired, dict):
            result = repaired
        elif isinstance(repaired, str):
            result = json.loads(repaired)
        else:
            raise ValueError(
                f"json_repair could not recover a dict from LLM output:\n{raw_text}"
            )

    # Validate required keys
    required = {"category", "confidence", "hypothesis", "evidence_lines"}
    missing = required - result.keys()
    if missing:
        raise ValueError(f"LLM response missing required keys: {missing}. Got: {result}")

    # Coerce types
    result["confidence"] = float(result["confidence"])
    if not isinstance(result["evidence_lines"], list):
        result["evidence_lines"] = [str(result["evidence_lines"])]

    valid_categories = {"Regression", "Flaky", "Environment", "Lint/Syntax", "Infra"}
    if result["category"] not in valid_categories:
        raise ValueError(
            f"LLM returned unknown category '{result['category']}'. "
            f"Must be one of: {valid_categories}"
        )

    return result


def classify_log(cleaned_log: str, correlation: dict, extra_context: Optional[str] = None) -> dict:
    """
    Sends the cleaned log, correlation context, and optional source context to Groq (Llama 3.3 70B)
    and returns a structured classification result.

    Args:
        cleaned_log: The cleaned CI failure log text from the runs table.
        correlation: The dict returned by correlate_run():
                     {any_file_in_diff, matched_files, hint}

    Returns:
        {
            "category":       str,   # One of the 5 taxonomy categories
            "confidence":     float, # 0.0 - 1.0
            "hypothesis":     str,   # One-sentence root cause
            "evidence_lines": list   # Up to 5 verbatim log lines
        }
    """
    api_key = _load_groq_key()
    client = Groq(api_key=api_key)

    user_message = _build_user_message(cleaned_log, correlation, extra_context)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        temperature=0.1,   # Low temperature for deterministic, consistent output
        max_tokens=512,
        response_format={"type": "json_object"},  # Groq native JSON mode
    )

    raw_text = response.choices[0].message.content
    return _parse_response(raw_text)


CONTRADICTION_SIGNALS = {
    "SyntaxError": "Lint/Syntax",
    "IndentationError": "Lint/Syntax",
    "ModuleNotFoundError": "Environment",
    "ImportError": "Environment",
    "No matching distribution": "Environment",
    "Could not find a version": "Environment",
    "Unable to resolve action": "Infra",
    "Out of disk space": "Infra",
}

def _needs_retry(result: dict) -> bool:
    """
    Checks if classification results require a retry.
    Triggers retry if LLM confidence is low (< 0.6) or if evidence lines
    deterministically contradict the classification category.
    """
    if result.get("confidence", 1.0) < 0.6:
        print(f"[Retry Check] Low confidence: {result.get('confidence')}. Triggering retry.")
        return True

    category = result.get("category")
    evidence_lines = result.get("evidence_lines", [])
    evidence_text = "\n".join(evidence_lines)

    for keyword, expected_category in CONTRADICTION_SIGNALS.items():
        if keyword in evidence_text and category != expected_category:
            print(f"[Retry Check] Contradiction: Found keyword '{keyword}' in evidence, "
                  f"but category is '{category}' (expected '{expected_category}'). Triggering retry.")
            return True

    return False

def classify_run(run_id: str, repo: str, db_path: str = "triage.db") -> dict:
    """
    Retrieves run from DB, performs log correlation, runs LLM classification
    with potential context-fetch and retry loops, and stores output in DB.
    """
    from ingest import get_run, save_classification
    from agent.correlate import correlate_run
    from agent.flaky import check_flaky_override

    run = get_run(run_id, repo, db_path=db_path)
    if not run:
        raise ValueError(f"Run ID {run_id} for repository {repo} not found in database.")

    # 1. Run flaky override check
    if check_flaky_override(run_id=run_id, repo=repo):
        result = {
            "category": "Flaky",
            "confidence": 1.0,
            "hypothesis": "Flaky override triggered: adjacent run passed with no relevant diff changes nearby.",
            "evidence_lines": [],
            "overridden": True
        }
        save_classification(
            run_id=run_id,
            repo=repo,
            category=result["category"],
            confidence=result["confidence"],
            hypothesis=result["hypothesis"],
            evidence=result["evidence_lines"],
            overridden=True,
            db_path=db_path
        )
        return result

    cleaned_log = run["cleaned_log"]
    changed_files = run["changed_files"]
    commit_sha = run["commit_sha"]

    # 2. Run deterministic correlation logic
    correlation = correlate_run(cleaned_log, changed_files)

    # 3. Call LLM to classify failure (Initial classification)
    initial_result = classify_log(cleaned_log, correlation)
    
    result = initial_result.copy()
    retries_run = 0
    max_retries = 2
    context = None

    # Loop up to max_retries if classification needs retry
    while _needs_retry(result) and retries_run < max_retries:
        retries_run += 1
        print(f"[Retry Loop] Classification needs retry (Confidence: {result['confidence']:.2f}, Category: {result['category']}). Attempt {retries_run} of {max_retries}...")

        # Fetch extra source context on the first retry
        if context is None:
            from agent.context_fetch import fetch_context_for_run
            context = fetch_context_for_run(
                log_text=cleaned_log,
                evidence_lines=result["evidence_lines"],
                repo=repo,
                commit_sha=commit_sha
            )
            if context:
                print(f"[Retry Loop] Successfully fetched context for retry:\n{context[:300]}...")
            else:
                print("[Retry Loop] No extra context could be fetched for retry. Proceeding anyway.")

        result = classify_log(cleaned_log, correlation, extra_context=context)

    result["overridden"] = False

    # Store initial details if retry successfully changed the result
    if retries_run > 0 and (result["category"] != initial_result["category"] or result["confidence"] != initial_result["confidence"]):
        result["initial_category"] = initial_result["category"]
        result["initial_confidence"] = initial_result["confidence"]
    else:
        result["initial_category"] = None
        result["initial_confidence"] = None

    # 4. Save result back to classifications table
    save_classification(
        run_id=run_id,
        repo=repo,
        category=result["category"],
        confidence=result["confidence"],
        hypothesis=result["hypothesis"],
        evidence=result["evidence_lines"],
        overridden=False,
        initial_category=result["initial_category"],
        initial_confidence=result["initial_confidence"],
        db_path=db_path
    )

    return result

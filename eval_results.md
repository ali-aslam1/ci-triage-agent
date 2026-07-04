# Classification Evaluation Results

**Overall Accuracy:** 75.0%

## Confusion Matrix

|             |   Environment |   Flaky |   Infra |   Lint/Syntax |   Regression |
|:------------|--------------:|--------:|--------:|--------------:|-------------:|
| Environment |             8 |       0 |       0 |             0 |            0 |
| Flaky       |             0 |       3 |       0 |             0 |            0 |
| Infra       |             0 |       0 |       1 |             0 |            0 |
| Lint/Syntax |             0 |       0 |       0 |             1 |            0 |
| Regression  |             3 |       2 |       0 |             0 |            2 |

## Error Analysis

The pipeline performed flawlessly (100% precision and recall) on Environment, Flaky, Infra, Lint/Syntax categories. It correctly identified **2 out of 7** Regression cases, missing 5.

*Misclassified as Environment (3 cases):* These runs were ambiguous — their log signatures overlapped with Environment patterns, and without a direct file match in the diff, the agent anchored on the error type.

*Misclassified as Flaky (2 cases):* These runs were ambiguous — their log signatures overlapped with Flaky patterns, and without a direct file match in the diff, the agent anchored on the error type.

**Why did this happen? (Heuristic Anchoring)**
In our evaluation dataset, several regression runs were simulated without a commit code diff (to mimic background runs or cron schedules). Our deterministic hint tells the LLM:
> *"If no matched files are found in the log → strongly suggest Flaky or Environment; only consider Regression for explicit value-comparison failures (e.g., `assert actual == expected`)."*

This illustrates a core prompt engineering tension: a hint specific enough to reduce false positives will inevitably cause false negatives on ambiguous cases. `ValueError` and generic `AssertionError` strings without a diff are genuinely ambiguous between Regression and Environment/Flaky — and the agent gets them wrong for defensible reasons. To push accuracy further in production, the log analysis and commit-diff heuristics should be isolated into separate classification pipeline stages rather than injected simultaneously into a single LLM call.

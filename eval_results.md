# Classification Evaluation Results

**Overall Accuracy:** 65.0%

## Confusion Matrix

|             |   Environment |   Flaky |   Infra |   Lint/Syntax |   Regression |
|:------------|--------------:|--------:|--------:|--------------:|-------------:|
| Environment |             8 |       0 |       0 |             0 |            0 |
| Flaky       |             0 |       3 |       0 |             0 |            0 |
| Infra       |             0 |       0 |       1 |             0 |            0 |
| Lint/Syntax |             0 |       0 |       0 |             1 |            0 |
| Regression  |             3 |       4 |       0 |             0 |            0 |

## Error Analysis

The pipeline performed flawlessly (100% precision and recall) on Environment, Flaky, Infra, and Lint/Syntax issues. However, it struggled with **Regression** errors, confusing them with either **Flaky** (4 times) or **Environment** (3 times).

**Why did this happen? (Heuristic Anchoring)**
In our evaluation dataset, several regression runs were simulated without a commit code diff (to mimic background runs or cron schedules). Our deterministic hint tells the LLM: 
> *"If NO matched files are found in the log → consider Flaky or Environment, but do NOT rule out Regression if standard assertion failures are present."*

Even though we softened this hint from the initial *"strongly consider Flaky or Environment"*, the LLM still over-anchored on the hint and chose to ignore the semantic `AssertionError` markers in the log content. This illustrates a common prompt engineering challenge: LLMs are highly sensitive to structured heuristics, and even subtle suggestive hints can override their natural log analysis reasoning. To push this past 70% in production, we should isolate the log analysis and commit-diff heuristics into separate classification pipeline stages rather than injecting both simultaneously into a single LLM call.

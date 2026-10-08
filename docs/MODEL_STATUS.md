# Model status

Nothing in this repository is clinically validated. Every model below is a research/demonstration
component. Statuses use the registry vocabulary; the UI shows the status next to every result.

## Heart-risk vitals model (the one runnable model)

| | |
|---|---|
| Purpose | Demonstrate end-to-end decision support and federated training on tabular vitals. Not for diagnosis. |
| Input | 8 vitals features (Module 1 schema). With the public UCI data only **age, systolic BP and heart rate** carry real values; the other 5 are fixed constants, so the model can only learn from those 3. |
| Output | A class (1 = positive outcome label as recorded by the contributing hospitals) and a raw model score. The score is **not calibrated** and is not a probability of disease. |
| Dataset | Public UCI Heart Disease (Cleveland), 303 records, vendored with a sha256 integrity check (`module3-fedlearning/uci_heart.py`), split across 2 seeded hospitals and uploaded through Modules 1 and 2. |
| **Served model** | **The currently PROMOTED model from the Module 7 registry** (`vitals-fedavg-logreg`, SGD logistic regression, FedAvg). Module 8 reads it at analysis time (≤ 5 s cache), re-hashes the weights, and shows its version, federated=true, artifact hash, round, hospital count and gate metrics in every report. Status shown: `DEPLOYED` = passed the platform's engineering gate and was promoted by a super_admin; **not clinically validated** (stated in the report). |
| Fallback | If, and only if, `FEDHEAL_ALLOW_DEMO_MODEL=true` (explicit in every environment, no implicit dev default) and nothing is promoted, Module 8 uses a model fitted at start-up on the same public data. Reports label it **NON-CLINICAL DEMO MODEL**, `status FALLBACK`, `federated false`. If the registry is unreachable the fallback is not used silently: without the flag the answer is `MODEL_UNAVAILABLE`. |
| Nothing promoted, flag off | `MODEL_UNAVAILABLE` (HTTP 503). No prediction. |
| Explanation | Promoted linear model: per-feature contribution to the log-odds (coefficient × normalised value), exact for that model, labelled `linear_contributions` (not SHAP, not causal). Fallback model: SHAP. |
| Status | Promoted federated model: `DEPLOYED` only after gate + explicit promotion; the model recorded below was **rejected** under the default gate policy. |

### Recorded federated run (2 hospitals, public UCI data, seed 42, 8 rounds, one run on 2026-10-06)

| Metric | Value |
|---|---|
| Global-holdout accuracy of the federated model | 0.591 (n = 44) |
| Always-predict-majority floor | 0.545 |
| Local-only baseline (hospitals trained alone, same holdout) | 0.534 |
| Per-hospital accuracy of the global model on each hospital's local test split | 0.552 / 0.900 |
| Validation gate, default policy | **FAIL** (accuracy 0.591 < 0.60 minimum; n_eval 44 < 50; not ≥ 0.05 above the majority floor; between-hospital gap 0.348 > 0.25) |
| Validation gate, relaxed TEST policy (`tests/integration/test_federation_flow.py` only) | PASS → promoted → served by Module 8 with demo fallback disabled. This proves the wiring, not that the model is good. |

These numbers come from a real run of `tests/integration/test_federation_flow.py` (the same numbers on repeated runs: fixed seed). They mean the
pipeline works and the gate does its job; they do **not** mean the model is useful. n = 44 is small
and the result will move with a different split. Do not quote them as clinical performance.

## Other specialists (Module 5/6)

Chest X-ray, retina, skin, CT, histopathology, RadFM, BiomedParse, SegVol, OmiCLIP, Evo 2 and the
leukemia/genomic models are **STUB** or **UNAVAILABLE** in this release (they need torch, weights and
validation data that this repository does not contain). Conditions that need them return
`MODEL_UNAVAILABLE`. Uploaded scans are stored and linked to the case and reported as
`UPLOADED — analysis UNAVAILABLE`; no image finding is ever generated.

## Gate thresholds are engineering defaults

`FEDHEAL_GATE_*` environment variables (min accuracy 0.60, min 50 eval examples, max regression 0.02,
min 2 hospitals, max between-hospital gap 0.25, min margin over majority 0.05) are demo thresholds, not
clinical acceptance criteria. Metrics are reported by the training side (Module 3) from its own held-out
evaluation; the registry stores and gates them but does not re-measure them.

Never claim: accurate, clinically proven, hospital-ready, FDA approved, medically certified.

# Model status

Nothing in this repository is clinically validated. Every model below is a research/demonstration
component. Statuses use the registry vocabulary; the UI shows the status next to every result.

## Heart-risk vitals model (the one runnable model)

| | |
|---|---|
| Purpose | Demonstrate end-to-end decision support and federated training on tabular vitals. Not for diagnosis. |
| Input | 8 vitals features (Module 1 schema). Only **age, systolic BP and heart rate** carry real values in the public training data; the other 5 are fixed constants, so the model can only learn from those 3. |
| Output | A class label and a raw model score. The score is **not calibrated** and is not a probability of disease. |
| Dataset | Public UCI Heart Disease (Cleveland), 303 records, vendored with a sha256 integrity check (`module3-fedlearning/uci_heart.py`). |
| Served model | `xgboost-vitals-v1`, version `uci-cleveland-demo-1`, **status FALLBACK** (`training_status=demo_fit`): fitted at service start on the public data. It is not hospital-trained and not federated. |
| Federated model | `vitals-fedavg-logreg` (SGD logistic regression, FedAvg across hospitals). Produced by `simulate_real.py`, registered as a **CANDIDATE** in Module 7. **No federated model is served for inference yet**; Module 8 does not load registry models. |
| Explanation | SHAP feature contributions for the vitals inputs. Explains the model, not the patient; not causal. |
| Status | FALLBACK (served). Federated candidate: REJECTED by the gate in the recorded run below. |

### Recorded federated run (2 hospitals, public UCI data, seed 42, 8 rounds, one run on 2026-10-06)

| Metric | Value |
|---|---|
| Global-holdout accuracy of the federated model | 0.591 (n = 44) |
| Always-predict-majority floor | 0.545 |
| Local-only baseline (hospitals trained alone, same holdout) | 0.534 |
| Per-hospital accuracy of the global model on each hospital's local test split | 0.552 / 0.900 |
| Validation gate | **FAIL** (n_eval 44 < 50; accuracy not ≥ 0.05 above the majority floor; between-hospital gap 0.348 > 0.25) |

These numbers come from a real run of `tests/integration/test_federation_flow.py`. They mean the
pipeline works and the gate does its job; they do **not** mean the model is useful. n = 44 is small
and the result will move with a different split. Do not quote them as clinical performance.

## Other specialists (Module 5/6)

Chest X-ray, retina, skin, CT, histopathology, RadFM, BiomedParse, SegVol, OmiCLIP, Evo 2 and the
leukemia/genomic models are **STUB** or **UNAVAILABLE** in this release (they need torch, weights and
validation data that this repository does not contain). Conditions that need them return
`MODEL_UNAVAILABLE`. They are never shown as results.

## Gate thresholds are engineering defaults

`FEDHEAL_GATE_*` environment variables (min accuracy 0.60, min 50 eval examples, max regression 0.02,
min 2 hospitals, max between-hospital gap 0.25, min margin over majority 0.05) are demo thresholds, not
clinical acceptance criteria. Metrics are reported by the training side (Module 3) from its own held-out
evaluation; the registry stores and gates them but does not re-measure them.

Never claim: accurate, clinically proven, hospital-ready, FDA approved, medically certified.

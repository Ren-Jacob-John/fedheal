# FedHeal data contract: vitals → model → synthesis

Written during the Module 1→2→3→5→6→8 integration pass, from what the code
actually does (not from what earlier READMEs implied).

## The decision

**Module 8's vitals specialist consumes Module 1's actual stored vitals
schema (option A).** There is no separate "heart-disease feature schema".
Evidence: Module 3's real-data path (`real_data.FEATURE_KEYS`) already trains
on exactly these fields; the development plan's Sprint C goal is "upload →
route → synthesize → view on real vitals data"; and `uci_heart.py` seeds
Cleveland data *into* this schema.

What looked like option B was a leftover: the names
`age, resting_bp, cholesterol, max_heart_rate, bmi, glucose, num_medications,
prior_admissions` came from Module 3's synthetic `make_classification`
partitions (`data.py`), where they were only labels on random columns.
Module 5 and Module 8 inherited those labels, so SHAP output and the
dashboard form were naming features (`cholesterol`, `glucose`,
`prior_admissions`) that **exist nowhere in Module 1**.

## The fields, per module

| Module | Fields | Notes |
|---|---|---|
| 1 `StoredVitalsOut` / `vitals_records` | `age_years`, `height_cm`, `weight_kg`, `systolic_bp`*, `diastolic_bp`*, `heart_rate_bpm`*, `medication_count`, `medication_mg_total`, `label`*, `label_source`, `validation_status`, `patient_ref`, `id` | `*` nullable. Module 2 allows a record without the three vitals. |
| 2 `VitalsRecord` | same 8 + optional `label` | Rejects out-of-range/inconsistent; flags soft outliers. |
| 3 real path `real_data.FEATURE_KEYS` | `age_years, systolic_bp, diastolic_bp, heart_rate_bpm, weight_kg, height_cm, medication_count, medication_mg_total` (fixed normalisation) | Logistic regression via FedAvg. **No global model is persisted/exported.** |
| 3 synthetic `data.FEATURE_NAMES` | `age, resting_bp, cholesterol, max_heart_rate, bmi, glucose, num_medications, prior_admissions` | Names on random data. Simulation only. |
| 5 `tabular_vitals` / `tabular_vitals_tabpfn` | **now** the Module 1 names above, same order | Was the synthetic names. Declared as `feature_names` on the specialist. |
| 6 `ConditionRouter` | validates `case["features"]` against the specialist's `feature_names` | Missing → `IncompleteDataError`. |
| 8 `feature_mapper.VITALS_MAPPING` | one identity row per model feature | See below. |

`N_FEATURES` is still 8 and the order is unchanged, so Modules 3/5/6 keep
their shapes.

## Feature mapper (Module 8: `feature_mapper.py`)

```
Module 1 stored record ─► map_record() ─► features[8] (None where missing) ─► Module 6 ─► Module 5 specialist
```

| Model feature | Module 1 field | Transform | Unit |
|---|---|---|---|
| `age_years` | `age_years` | identity | years |
| `systolic_bp` | `systolic_bp` | identity | mmHg |
| `diastolic_bp` | `diastolic_bp` | identity | mmHg |
| `heart_rate_bpm` | `heart_rate_bpm` | identity | beats/min |
| `weight_kg` | `weight_kg` | identity | kg |
| `height_cm` | `height_cm` | identity | cm |
| `medication_count` | `medication_count` | identity | count |
| `medication_mg_total` | `medication_mg_total` | identity | mg |

Rules: no unit conversion, no imputation, no derived value, no renaming a
field to a different clinical concept. `label`, `label_source`, `patient_ref`,
`id`, `validation_status` are never inputs. A null/absent/NaN field is
**missing**; a non-numeric one is **invalid**. `verify_mapping()` runs at
startup and fails if the table and the specialist's declared names ever
diverge.

Legacy names with **no** Module 1 source: `cholesterol`, `glucose`,
`prior_admissions` (and `max_heart_rate`, a stress-test maximum, which is not
the recorded `heart_rate_bpm`). They are not mapped, not defaulted, and not
accepted anywhere.

## Responses

| Situation | HTTP | `detail.status` |
|---|---|---|
| Valid, complete, validated record | 200 | `ok` |
| A model feature is null/absent | 422 | `incomplete_data` + `missing_features` |
| A stored value isn't a finite number | 422 | `invalid_feature_values` |
| Record is `flagged` (awaiting review) | 409 | `record_not_validated` |
| Unknown condition | 404 | `unknown_condition` + `known_conditions` |
| Condition needs non-vitals inputs (imaging, genomics, CBC) | 422 | `unsupported_input` + specialist status cards (stub flags visible) |
| Specialist has no model loaded | 503 | `specialist_unavailable` |
| Record belongs to another hospital / doesn't exist | 403 / 404 | `forbidden` / `record_not_found` |
| Module 1 unreachable | 502 | `upstream_unreachable` |

Success body: `record`, `inputs` (feature, source field, value, unit),
`specialist` (+ `model_name`, `model_version`, `is_stub`, `is_fallback`,
`training_status`, `feature_names`), `model` (source, `federated`,
`hospital_trained`, description), `prediction`, `explanation`
(`status` = `available`|`unavailable`, `reason`, `contributions[{feature,value,contribution}]`),
`warnings[{code,message}]`, and the existing `synthesis` report.

## Model status — what each value means

`training_status`: `untrained` (real class, not fitted: predict refuses) ·
`none` (stub: no model exists) · `demo_fit` (fitted on public/demo data) ·
`synthetic_demo` (fitted on random noise to exercise the pipeline) ·
`federated` (reserved for Module 3's global model — **nothing sets this yet**) ·
`unknown` (not declared by that specialist).

**Module 8's vitals model today:** Module 3 does not export its global model,
so there is nothing federated to load. Module 8 uses an isolated demo
fallback (`model_provider.py`): the vendored public UCI Cleveland data in
Module 1's schema. Only age, systolic BP and heart rate carry real values in
it (the other five are constants), so the model can learn from 3 features.
It is reported as `demo_fit`, `is_fallback=true`, `federated=false`. Outside
local development it is **off** unless `FEDHEAL_ALLOW_DEMO_MODEL=true`; with
it off the endpoint answers 503. The previous behaviour — fitting on
`numpy.random.normal` noise at import and presenting it as a heart-disease
model — is removed.

**Integrating Module 3 later:** add an export step to Module 3, load it in
`model_provider.py`, and set `training_status="federated"`,
`is_fallback=False`. Nothing else in this chain needs to change.

## Explanations

* SHAP values are labelled **only** from the specialist's declared
  `feature_names`; a count mismatch raises (reported as unavailable) instead
  of zip-truncating or inventing names. They are log-odds toward the
  **positive class** (`high_risk`), whichever class was predicted — the UI
  says so.
* If SHAP can't run (not installed, incompatible model such as TabPFN) the
  response has `explanation.status = "unavailable"` with the reason, and no
  contributions.
* The knowledge-graph note is a static `(modality, label) → text` lookup. It
  is tagged `data_driven: false` and shown in the UI as a reference note, not
  as an explanation of the record. (Its old vitals text mentioned glucose and
  medication load; it never saw those values.)

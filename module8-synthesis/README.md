# Module 8 — Synthesis / Review-Packet Layer

## What this is

Module 6 (condition router) returns a `ConditionReport`: a list of raw
specialist predictions + attached explanations, per condition. That's
correct output for *models*, but it isn't yet something a clinician can
scan in ten seconds. Module 8 is the layer in between: it aggregates
Module 5/6 output into a `SynthesisReport` — a structured summary meant
to sit in front of a clinician for review, never a standalone verdict.

## What this deliberately is NOT

Read this before extending the module — it encodes a real design
decision, not an oversight:

- **It does not emit a diagnosis.** The field is called
  `model_impression`, not `diagnosis`. Every report carries
  `requires_clinician_review = True` (hardcoded, not a config flag)
  and a `disclaimer` string that travels with the *data*, not just the
  printed report — so any downstream renderer (dashboard, PDF export,
  API response) inherits it automatically instead of needing to
  remember to add it.
- **It does not generate treatment pathways, drug names, dosages, or
  prognostic timelines.** Nothing in this pipeline — a metadata router,
  a handful of classifiers/segmenters, SHAP/Grad-CAM/rule-based
  explainers — has any basis for recommending therapy. Fabricating that
  layer on top would produce exactly the failure mode the rest of this
  codebase is deliberately built to avoid (see Module 5/6's
  `UnroutableCaseError` / `UnknownConditionError` docstrings: a
  confident wrong answer is worse than a clear "not enough
  information").
- **It does not invent a confidence number across modalities.** Where
  Module 5's `FusionLayer` has already computed a transparent, inspectable
  `overall_risk_score` from real per-specialist confidences, synthesis
  reports that number and shows its inputs. It never manufactures a new
  "precision metric" out of nothing — every number in the report traces
  back to a real specialist's `PredictionResult.confidence`.
- **It never silently drops missing or stub data.** `data_completeness`
  lists which of a condition's specialists had no case data supplied,
  and `used_any_stub_models` (and per-finding `is_stub`) is carried
  through so a stubbed placeholder result can never be mistaken for a
  trained model's output.

## Files

- `synthesis.py` — `SynthesisReport` dataclass + `build_synthesis()`,
  which wraps a Module 6 `ConditionReport` (optionally plus a Module 5
  `FusedAssessment`) into the reviewable structure above, and a
  `to_markdown()` renderer for the dashboard/CLI.
- `demo.py` — runs `build_synthesis()` against the same synthetic cases
  Module 6's `demo.py` uses (breast cancer, leukemia, diabetic
  retinopathy, heart disease, plus a partial-data and an unknown-condition
  case), so the aggregation logic is exercised end to end without any
  real patient data.

## Next sprint

- Wire this into Module 4's React dashboard as the actual rendered view
  for condition-routing results (the federation map, vitals upload, and
  super_admin operator views already live in `module4-dashboard-react`;
  synthesis is the main piece not yet connected). `to_markdown()` is a
  reasonable stand-in for a first integration.
- Add a persistence layer (Module 7 admin already has a DB) so a
  `SynthesisReport` can be stored with a clinician's eventual
  sign-off/override, closing the loop this module deliberately leaves
  open.

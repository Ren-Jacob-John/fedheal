# Module 8 — Synthesis / Review-Packet Layer: Full Explanation

## What this module is for

Module 6's `ConditionRouter` returns a `ConditionReport`: raw specialist
predictions plus attached explanations, per disease. That's correct output
for *models*, but it isn't something a clinician can scan in ten seconds.
This module sits in between: it aggregates Module 5/6 output into a
`SynthesisReport` — a structured summary meant for clinician review, never
a standalone verdict.

## How it works

- **`synthesis.py`** defines `SynthesisReport` and `build_synthesis()`:
  - Takes a Module 6 `ConditionReport` and optionally a Module 5
    `FusedAssessment` (from `FusionLayer.combine()`).
  - Produces `model_impression` (not `diagnosis`), `data_completeness`
    (which specialists had no case data), `used_any_stub_models`, and a
    combined risk score when fusion input is provided.
  - `requires_clinician_review = True` is **hardcoded**, not configurable.
  - `to_markdown()` renders a human-readable review packet for CLI or
    future dashboard display.
- **`demo.py`** exercises the same synthetic cases as Module 6's demo
  (breast cancer, leukemia, diabetic retinopathy, heart disease, plus
  partial-data and unknown-condition cases) without real patient data.

## What this deliberately is NOT

This encodes a real design decision, not an oversight:

- **No diagnosis** — the field is `model_impression`, with a disclaimer
  carried in the data structure itself.
- **No treatment pathways** — nothing in the upstream pipeline has basis
  for recommending therapy.
- **No invented cross-modality confidence** — every number traces to a
  real specialist's `PredictionResult.confidence` or Module 5's transparent
  `overall_risk_score`.
- **No silent stub hiding** — `is_stub` and `used_any_stub_models` are
  threaded through so placeholder results can't masquerade as trained-model
  output.

## How other modules depend on it

- **Depends on Module 6** for `ConditionReport` input (and optionally
  Module 5's `FusionLayer` for a combined risk score).
- **Module 4** will eventually render `SynthesisReport` output — not wired
  yet; see `SystemMap.jsx`'s "review packet (planned)" edge.
- **Module 7** is the natural home for persisting reports with clinician
  sign-off — not implemented yet.

## What's real vs. what's a known prototype simplification

Real: the full aggregation logic, markdown renderer, stub/completeness
threading, and end-to-end demo against Module 6's synthetic cases.

Documented as next-sprint work in this folder's `README.md`: wire into
Module 4's React dashboard, add persistence in Module 7 for clinician
sign-off/override, and clinical review of fusion severity weights that
feed the combined risk score.

# Module 2 — Data Ingestion & Validation: Full Explanation

## What this module is for

Federated learning's entire value proposition rests on one assumption:
that the data each hospital trains on locally is trustworthy. If one
hospital's data entry system has a bug that stores height in inches
instead of centimeters, or a form that lets `medication_dose` default to
some nonsense value, that bad data doesn't just hurt that one hospital —
once it's folded into the shared global model via federated averaging, it
quietly degrades the model *every* hospital uses. This module is the gate
that stands between "a hospital uploaded something" and "that something is
allowed to influence a model anyone relies on."

## How it works — five checks, in order

1. **De-identification screen.** Before anything else is even parsed, the
   raw upload is checked for forbidden field names — `name`, `address`,
   `ssn`, `dob`, `phone`, `email`, and similar. If any appear, that record
   is rejected outright. This runs on the raw dictionary, not the parsed
   schema, specifically so a forbidden field can't sneak through by being
   silently dropped during parsing.
2. **Schema validation.** Every surviving record has to match
   `schema.VitalsRecord` — the right fields, the right types (a pydantic
   model, so this is enforced automatically, not hand-coded).
3. **Plausibility range checks.** Is `age_years=180` physically possible?
   Is `height_cm=400`? Each field has a documented plausible range;
   anything outside it is rejected with a specific, human-readable reason.
4. **Cross-field consistency checks.** Some values only make sense in
   light of others — a newborn shouldn't be on a large combined medication
   dose, diastolic blood pressure shouldn't exceed systolic, a
   height/weight combination that implies a biologically implausible BMI
   usually means a unit mix-up (inches vs. centimeters, for instance).
5. **Batch-level outlier detection.** Everything that survives checks 1–4
   goes through an isolation forest across the whole batch. This is
   deliberately a *soft flag*, not a rejection — a record can be
   statistically unusual within its batch without being wrong, so it's
   marked for human review rather than silently dropped or silently
   trained on.

## What a validation result looks like

Every record ends up with one of three statuses: `passed` (clean),
`flagged` (passed the hard rules, but looked like a statistical outlier —
needs a human to look at it), or `rejected` (failed a hard rule, with the
specific reason attached). The whole-batch response reports totals for
each, plus a per-record breakdown.

## How other modules depend on it

- **Module 1** calls this service directly from its `POST /vitals/upload`
  endpoint — every hospital vitals upload passes through here before
  anything is stored. Module 1 deliberately doesn't reimplement any of
  these rules; it just forwards the raw records and trusts this module's
  answer.
- **Module 7** (admin) receives a best-effort, rolled-up count of what got
  flagged/rejected per hospital (never the underlying records — only a
  tally like "3 records rejected for out-of-range height") so a platform
  operator can see data-quality trends without ever seeing patient-level
  data.

## What's real vs. what's a known prototype simplification

Real: all five checks, the full pipeline, the reporting-to-Module-7
integration, a CSV upload endpoint (`POST /validate/vitals/csv`, sharing
the exact same `_validate_records` gate as the JSON path) alongside the
original JSON one, and a human review workflow for `flagged` records —
Module 1's `GET /vitals/flagged` + `POST /vitals/{id}/review` let a
hospital admin approve or reject each one, rather than this module's
count just sitting unreviewed. Documented as next-sprint work in this
folder's `README.md`: the same five-stage pipeline, adapted for imaging
metadata once the imaging track starts.

# Module 2 — Data Ingestion & Validation

## What this module is for

This is the quality gate every uploaded record must pass before it can
ever influence the shared federated model. Its entire job is to catch bad
data (identifying fields, physically impossible values, internally
inconsistent records, statistical outliers) **before** Module 3 trains on
it — a hospital's miscalibrated device or data-entry mistake should never
silently corrupt the model every other hospital shares.

## How it works internally

**Files:**
- `main.py` — the FastAPI app; the pipeline orchestration.
- `schema.py` — `VitalsRecord`, the pydantic schema every record must
  conform to (deliberately excludes anything identifying).
- `rules.py` — the three rule-based checks: forbidden fields,
  plausibility ranges, cross-field consistency.
- `anomaly.py` — the batch-level isolation-forest outlier flagger.
- `docs_theme.py` — cosmetic `/docs` theming, not functional logic.

**The 5-stage pipeline, run in this order for every batch:**

1. **De-identification screen** (`rules.check_forbidden_fields`) — if the
   raw uploaded record contains any key from `FORBIDDEN_FIELDS` (name,
   address, SSN, MRN, phone, email, date of birth, etc.), the whole record
   is rejected outright, before any value is even parsed. This is a hard
   boundary, not a data-quality signal.
2. **Schema validation** (`schema.VitalsRecord`, via pydantic) — checks
   required fields exist and are the right type (e.g. `age_years` is a
   number 0–130).
3. **Plausibility range checks** (`rules.check_plausible_ranges`) — is
   each value physically possible for a human? (e.g. `heart_rate_bpm`
   between 20 and 250, `weight_kg` between 0.5 and 400.) Out-of-range →
   hard reject.
4. **Cross-field consistency checks**
   (`rules.check_cross_field_consistency`) — do the fields agree with
   each other (e.g. systolic vs. diastolic blood pressure relationship)?
   Fails → hard reject.
5. **Batch-level outlier detection** (`anomaly.flag_outliers`) — an
   Isolation Forest run across the whole batch's numeric fields flags
   records that are *statistically* unusual relative to the rest of the
   batch, even if no single rule was broken (e.g. an entire hospital's
   upload is shifted because of a unit mismatch). This is a **soft flag**,
   not a rejection — flagged records still reach storage, but are surfaced
   to a human for review via Module 1's `/vitals/flagged` and Module 4's
   review panel. Needs at least ~10 records in the batch to be meaningful;
   smaller batches skip this stage.

Each record comes back from the pipeline as one of: `passed`, `flagged`,
or `rejected`, with the specific reason(s) attached.

## How to run it

```bash
cd module2-validation
pip install -r requirements.txt
uvicorn main:app --reload --port 8002
```

Interactive API docs: `http://localhost:8002/docs`

**Endpoints:**
- `POST /validate/vitals` — validate a JSON batch of records.
- `POST /validate/vitals/csv` — validate a CSV file upload.
- `GET /health` — liveness check.

This service has no database of its own and no required environment
variables beyond the optional Module 7 reporting URL — it's a stateless
pipeline: records in, per-record verdicts out. Module 1 owns storage of
the results.

## How it depends on / is depended on by other modules

- **Called by:** Module 1, for every vitals upload (JSON and CSV) before
  storing anything.
- **Reports to (best-effort):** Module 7 — a rolled-up **count** of flags
  per reason string, never a raw patient-level record, so the admin
  dashboard can show data-quality health without ever seeing patient data.
  If Module 7 is unreachable, validation still completes normally; the
  report is simply skipped.

## Known limitations / current status

- Fully functional, no known gaps in the pipeline logic itself.
- No automated tests yet — this is the highest-value module to add tests
  to first, since its correctness is what keeps bad data out of the
  shared model.
- Rejection reasons are returned per-request but not persisted anywhere
  independently queryable — currently reconstructable only from Module
  7's rolled-up counts, not from a full audit log.

# Module 2 — Data Ingestion & Validation

## Setup

```bash
pip install -r requirements.txt --break-system-packages
uvicorn main:app --reload --port 8002
```

## Pipeline order (see `main.py` docstring)

1. **De-identification screen** — hard reject if the raw upload contains a
   field like `name`, `address`, `ssn`, `dob`, etc. See `rules.FORBIDDEN_FIELDS`.
2. **Schema validation** — `schema.VitalsRecord` (pydantic) checks types and
   required fields.
3. **Plausibility range checks** — is `age_years=180` physically possible?
   See `rules.PLAUSIBLE_RANGES`.
4. **Cross-field consistency checks** — do fields agree with each other
   (e.g. medication dose vs. age, diastolic vs. systolic BP)?
5. **Batch outlier detection** — isolation forest flags records that are
   statistically unusual *within this batch*, even if no single rule caught
   them. This is a **soft flag for human review**, not an automatic rejection.

## Try it

```bash
curl -X POST localhost:8002/validate/vitals -H "Content-Type: application/json" -d '{
  "records": [
    {"patient_ref": "P-001", "age_years": 45, "height_cm": 175, "weight_kg": 80,
     "systolic_bp": 120, "diastolic_bp": 80, "medication_count": 1, "medication_mg_total": 50},
    {"patient_ref": "P-002", "age_years": 1, "height_cm": 400, "weight_kg": 8,
     "medication_count": 0, "medication_mg_total": 0},
    {"patient_ref": "P-003", "name": "Jane Doe", "age_years": 30, "height_cm": 165, "weight_kg": 60}
  ]
}'
```

You should see: `P-001` passed, `P-002` rejected (height 400cm is impossible),
`P-003` rejected (contains `name`).

## Next sprint (not yet done here, on purpose)

- CSV upload endpoint (`UploadFile`), not just JSON — hospitals will mostly
  upload CSV exports from their own systems.
- Wire the "passed" records to actually flow into Module 3's local training
  step instead of stopping here.
- Send "flagged" records to the hospital dashboard (Module 4) for a human
  to approve/reject rather than silently dropping them.
- Same pipeline, adapted for imaging metadata once the imaging track starts.

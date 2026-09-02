# Module 1 — Authentication & Multi-Tenancy

## Setup

```bash
pip install -r requirements.txt --break-system-packages
uvicorn main:app --reload --port 8001
```

Open http://localhost:8001/docs to try it interactively.

## Try it end-to-end

```bash
# 1. Create a hospital (tenant)
curl -X POST localhost:8001/hospitals -H "Content-Type: application/json" \
  -d '{"name": "General Hospital"}'
# -> {"id": "<hospital_id>", "name": "General Hospital", "is_active": true}

# 2. Register a clinician at that hospital
curl -X POST localhost:8001/register -H "Content-Type: application/json" \
  -d '{"email": "doc@general.com", "password": "hunter2", "hospital_id": "<hospital_id>"}'

# 3. Log in (note: OAuth2 form fields, not JSON, for /token)
curl -X POST localhost:8001/token -d "username=doc@general.com&password=hunter2"
# -> {"access_token": "<jwt>", "token_type": "bearer"}

# 4. Call a protected, hospital-scoped endpoint
curl localhost:8001/training-status -H "Authorization: Bearer <jwt>"

# 5. Upload vitals (forwarded to Module 2 for validation, then stored)
curl -X POST localhost:8001/vitals/upload -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"records": [{"patient_ref": "P-001", "age_years": 54, "height_cm": 170,
        "weight_kg": 78, "systolic_bp": 132, "diastolic_bp": 84,
        "heart_rate_bpm": 76, "medication_count": 1, "medication_mg_total": 50}]}'

# 6. (Module 3 only) export a hospital's stored, validated vitals
curl "localhost:8001/vitals/export?hospital_id=<hospital_id>" \
  -H "X-Service-Key: dev-only-internal-service-key"
```

## API contract (for Module 4 / dashboard team)

| Endpoint | Method | Auth? | Purpose |
|---|---|---|---|
| `/hospitals` | POST | no (lock down later) | Onboard a new hospital tenant |
| `/hospitals` | GET | no | List tenants |
| `/hospitals/{id}` | PATCH | super_admin JWT | Activate/deactivate a hospital (used by Module 7's operator view) |
| `/register` | POST | no | Create a user under a hospital |
| `/token` | POST | no | Login, get JWT (OAuth2 password form: `username`, `password`) |
| `/me` | GET | yes | Get current user's profile |
| `/vitals/upload` | POST | yes | Forward `{records: [...]}` to Module 2 for validation; store passed/flagged records under the caller's hospital |
| `/vitals/export` | GET | service key | Module 3-only: pull a hospital's stored validated vitals (`?hospital_id=&include_flagged=`) |
| `/training-status` | GET | yes | Real, DB-backed: validated record count + readiness per hospital (super-admin sees all) |

The JWT payload contains `sub` (user id), `hospital_id`, and `role` — decode
it client-side just to read the role for UI purposes, but always let the
server be the source of truth for what data a request can touch.

## Vitals pipeline (new this sprint)

`POST /vitals/upload` is the missing link the previous sprint's READMEs
called out: a hospital-scoped user posts raw vitals dicts here, this
service forwards them to Module 2 (`FEDHEAL_VALIDATION_API_URL`, default
`http://localhost:8002`) for the real validation rules, and only
`passed`/`flagged` records get stored — scoped to `current_user.hospital_id`,
never a client-supplied one. `GET /vitals/export` is how Module 3's
`real_data.py` reads that data back out for actual federated training,
gated by the same `X-Service-Key` shared-secret pattern Module 7 uses.

`/training-status` no longer reads from a fake in-memory dict — it counts
this hospital's stored `VitalsRecord` rows and reports `ready_for_training`
once there are at least `MIN_RECORDS_FOR_TRAINING` (10, in `main.py`).
Federated round history itself still lives in Module 7, which is the
module that actually talks to Module 3.

## Roles

- `super_admin` — you, the platform operator. Sees across hospitals.
- `hospital_admin` — manages that hospital's own users/data.
- `clinician` — uploads cases, views predictions for their hospital only.

## Using Supabase

This service can run against Supabase's managed Postgres instead of the
local SQLite fallback — nothing in `models.py` or `main.py` needs to
change, since Supabase *is* Postgres and SQLAlchemy just needs a
connection string.

1. In your Supabase project: **Project Settings → Database → Connection
   string**. Copy the **Session pooler** URI (this is a long-running
   FastAPI app, not a serverless function, so Session pooler is the right
   one — Transaction pooler is meant for short-lived connections).
2. `cp .env.example .env`, paste that URI into `FEDHEAL_DATABASE_URL`,
   and replace `[YOUR-PASSWORD]` with your actual database password.
3. `pip install -r requirements.txt --break-system-packages` (this now
   includes `psycopg2-binary`, the Postgres driver, and `python-dotenv`,
   which auto-loads `.env` — see `database.py`).
4. `uvicorn main:app --reload --port 8001` — on first run, SQLAlchemy
   creates the `hospitals`, `users`, and `vitals_records` tables in your
   Supabase project automatically (`Base.metadata.create_all` in
   `main.py`), same as it does for SQLite. No manual migration needed at
   this stage.

Leave `FEDHEAL_DATABASE_URL` unset (or skip the `.env` file entirely) and
this falls straight back to a local SQLite file — useful for a teammate
who wants to test something quickly without a Supabase project set up.

**Module 7 (admin)** can point at the same Supabase project — its tables
(`training_rounds`, `validation_flags`) don't collide with this module's
table names. See `module7-admin/.env.example`.

## Next sprint (not yet done here, on purpose)

- Add Alembic migrations. Right now `Base.metadata.create_all` creates
  tables on first run but has no story for evolving a schema that already
  has data in it (e.g. adding a column to `vitals_records` later) —
  fine for a fresh Supabase project today, not once real data exists.
- Rate limiting / lockout on `/token`.
- Add a real diagnosis/outcome field to the vitals upload flow — right now
  `label` is optional and Module 3 falls back to a rule-based placeholder
  when it's missing (see `module3-fedlearning/real_data.py`'s docstring).
  This is the actual gap standing between "the pipeline runs end-to-end"
  and "the model output means anything clinically."
- Lock down CORS `allow_origins` to the real dashboard origin.

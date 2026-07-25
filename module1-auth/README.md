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
```

## API contract (for Module 4 / dashboard team)

| Endpoint | Method | Auth? | Purpose |
|---|---|---|---|
| `/hospitals` | POST | no (lock down later) | Onboard a new hospital tenant |
| `/hospitals` | GET | no | List tenants |
| `/register` | POST | no | Create a user under a hospital |
| `/token` | POST | no | Login, get JWT (OAuth2 password form: `username`, `password`) |
| `/me` | GET | yes | Get current user's profile |
| `/training-status` | GET | yes | Hospital-scoped status (super-admin sees all) |

The JWT payload contains `sub` (user id), `hospital_id`, and `role` — decode
it client-side just to read the role for UI purposes, but always let the
server be the source of truth for what data a request can touch.

## Roles

- `super_admin` — you, the platform operator. Sees across hospitals.
- `hospital_admin` — manages that hospital's own users/data.
- `clinician` — uploads cases, views predictions for their hospital only.

## Next sprint (not yet done here, on purpose)

- Swap SQLite for Postgres, add Alembic migrations.
- Rate limiting / lockout on `/token`.
- Replace `FAKE_TRAINING_STATUS_DB` with real reads from Module 3's aggregation server.
- Lock down CORS `allow_origins` to the real dashboard origin.

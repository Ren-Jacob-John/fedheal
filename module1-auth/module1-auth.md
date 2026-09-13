# Module 1 — Authentication & Multi-Tenancy

## What this module is for

This is the foundation module every other service trusts. It answers one
question authoritatively for the whole platform: **which hospital, and
which role, does this request belong to?** Every other module (validation,
training, admin, dashboard) treats the JWT this service issues as the only
source of truth for that — never a client-supplied hospital ID, which
would let one hospital impersonate another simply by editing a request.

It also owns the vitals-upload entry point: a hospital's upload lands here
first, gets forwarded to Module 2 for validation, and only validated
records are stored against that hospital.

## How it works internally

**Files:**
- `main.py` — the FastAPI app: all HTTP endpoints.
- `auth.py` — password hashing (bcrypt) and JWT encode/decode helpers.
- `models.py` — SQLAlchemy ORM models (Hospital, User, StoredVitalsRecord).
- `database.py` — engine/session setup; defaults to SQLite for local dev,
  reads `FEDHEAL_DATABASE_URL` for Postgres/Supabase in staging/prod.
- `docs_theme.py` — cosmetic: a custom `/docs` (Swagger UI) theme, not
  functional logic.
- `.env.example` — every environment variable this service reads.

**Request flow for login:**
1. `POST /token` (OAuth2 password flow) — username/password checked
   against the hashed password in `models.User`.
2. On success, a JWT is issued carrying the user's hospital ID and role
   (`hospital_admin` or `super_admin`). It's returned in the JSON body
   **and** set as an httpOnly cookie (`fedheal_token`) so the dashboard's
   JavaScript never has direct read access to it (a defense against XSS
   token theft — the earlier design kept the token in `localStorage`,
   which this replaced).
3. A sliding-window rate limiter (in-memory, keyed by IP + username) caps
   login attempts at 5 per 60 seconds per key, independent of how busy the
   shared IP is otherwise (important for hospitals behind one NAT'd
   office connection).

**Request flow for a vitals upload:**
1. `POST /vitals/upload` (JSON) or `POST /vitals/upload/csv` (CSV file) —
   requires a valid token; the hospital ID is taken **only** from the
   token, never from the request body.
2. Each record is forwarded to Module 2 (`FEDHEAL_VALIDATION_API_URL`,
   default `http://localhost:8002`) for the 5-stage validation pipeline.
3. Records that come back `passed` or `flagged` are stored in
   `StoredVitalsRecord` against that hospital; `rejected` records are
   reported back to the uploader with the rejection reason but never
   stored.
4. `GET /vitals/flagged` and `POST /vitals/{record_id}/review` let a
   hospital admin see and clear flagged records from the dashboard.
5. `GET /vitals/export` is a **service-to-service** endpoint (guarded by a
   shared secret, `FEDHEAL_SVC_KEY_M3_M1`) that only Module 3's
   `real_data.py` calls, to pull validated records for federated training
   — no human-facing client should call this.
6. `GET /training-status` reports whether a hospital has at least
   `MIN_RECORDS_FOR_TRAINING` (10) stored records — an honest floor so the
   dashboard never claims "ready" after a single test upload.

**Multi-tenancy / hospital management:** `POST /hospitals`, `GET
/hospitals`, `PATCH /hospitals/{id}` — super-admin-only endpoints to
create hospitals and toggle their active status.

## How to run it

```bash
cd module1-auth
pip install -r requirements.txt
cp .env.example .env        # then fill in real values, or leave DB URL
                             # unset to fall back to local SQLite
uvicorn main:app --reload --port 8001
```

Interactive API docs: `http://localhost:8001/docs`

**Required environment variables** (see `.env.example` for the full,
commented list):
- `FEDHEAL_DATABASE_URL` — Postgres/Supabase connection string; omit for
  SQLite fallback.
- `FEDMED_JWT_SECRET` — **must be identical** across every FedHeal service
  that verifies this token (Modules 1 and 7).
- `FEDHEAL_SVC_KEY_M3_M1` — shared secret Module 3 uses to call
  `/vitals/export`.
- `FEDHEAL_VALIDATION_API_URL` — where Module 2 is reachable.
- `FEDHEAL_DASHBOARD_ORIGIN` — comma-separated list of allowed CORS
  origins (the dashboard's actual URL(s)).
- `FEDHEAL_COOKIE_SECURE` — set `true` once served over HTTPS.

## How it depends on / is depended on by other modules

- **Calls out to:** Module 2 (validation), on every upload.
- **Called by:** Module 4 (dashboard) for every login/upload/review
  action a hospital user takes; Module 3's `real_data.py` for
  `/vitals/export`; Module 7 (admin) proxies some hospital-oversight calls
  here.
- **Nobody else should ever accept a hospital ID except from this
  module's token** — that invariant is the entire point of the module.

## Known limitations / current status

- The login rate limiter is in-memory and per-process — fine for a
  single-worker deployment, but limits reset independently per worker in
  a multi-process deployment. Needs a shared store (Redis) before scaling
  workers horizontally.
- No automated tests yet.
- No `/health` endpoint (Modules 2 and 7 have one; this module doesn't
  yet) — worth adding for deployment health checks.

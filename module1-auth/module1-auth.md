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

### Database schema — Alembic (Sprint A set up, Sprint B finished)

Schema changes moved from `Base.metadata.create_all()` to Alembic
migrations. Sprint A set this up transitionally (both mechanisms live,
gated by `FEDHEAL_AUTO_CREATE_TABLES`); **Sprint B removes `create_all`
and that variable entirely** — `alembic upgrade head` is now the only way
tables come into existence, in every environment, local dev included.

```bash
# FRESH database (nothing there yet):
alembic upgrade head

# EXISTING database that create_all already built (every local SQLite
# file and the pre-Sprint-B Supabase project): tell Alembic it's already at
# the baseline, THEN apply the new migrations.
alembic stamp 0001_baseline
alembic upgrade head

# Review the SQL before it touches staging/prod:
alembic upgrade head --sql

# After changing models.py:
alembic revision --autogenerate -m "what changed"
```

Alembic reads `FEDHEAL_DATABASE_URL` — the same env var `database.py`
reads — so `alembic upgrade head` can never migrate a different database
than the app is about to write to. `alembic.ini` deliberately leaves
`sqlalchemy.url` empty; the Supabase password does not belong in version
control.

**Check before you stamp.** Stamping a database that does NOT have the
tables leaves Alembic believing they exist, and the baseline migration
will then be skipped forever. `sqlite3 fedmed_auth.db ".tables"` or `\dt`
in psql first.

**Every environment now needs its migrations applied before `uvicorn
main:app` is started against it** — there is no more `create_all` safety
net. Staging: `alembic stamp 0001_baseline && alembic upgrade head`
against the staging `FEDHEAL_DATABASE_URL` (staging was built by
`create_all` too, same as every local SQLite file) — see the Sprint B
deployment checklist in `docs/DEVELOPMENT_PLAN.md` section 7.

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

`GET /health` returns `{"status": "ok"}` — added in Sprint B so every
module now has the same deployment health-check shape (Modules 2 and 7
already had one).

## How it depends on / is depended on by other modules

- **Calls out to:** Module 2 (validation), on every upload.
- **Called by:** Module 4 (dashboard) for every login/upload/review
  action a hospital user takes; Module 3's `real_data.py` for
  `/vitals/export`; Module 7 (admin) proxies some hospital-oversight calls
  here.
- **Nobody else should ever accept a hospital ID except from this
  module's token** — that invariant is the entire point of the module.

### Label provenance (new in Sprint A)

Two columns were added so "is this label a real clinical outcome?" is
answerable from the database rather than inferred:

- `hospitals.requires_label` — an explicit per-tenant declaration that
  this hospital has real outcomes. When true, Module 2 **rejects** any
  uploaded record without a `label` (`rules.check_required_label`), so a
  broken EHR export is caught at upload time by the person who can fix
  it, instead of at training time by someone else. Defaults false, which
  preserves the previous behaviour for existing tenants — it's a decision
  each hospital makes, not something to infer from whether labels happen
  to show up.
- `vitals_records.label_source` — `"hospital"` or `"missing"`. There is
  deliberately **no** `"placeholder"` value: Module 3's rule-based
  placeholder label is computed at training time and never written back
  here, so this column can't ever assert that a made-up label is a
  clinical fact.

`GET /vitals/export` now defaults to `labeled_only=true` — **a breaking
default change**. Previously it returned unlabeled records too and
Module 3 quietly substituted a placeholder label for each, which made the
default end-to-end path train partly on labels no clinician produced.
Pass `labeled_only=false` for the old behaviour.

`GET /training-status` gained `labeled_records`, `unlabeled_records`,
`label_coverage`, and a new `awaiting_labels` status — a hospital sitting
on 500 unlabeled records used to report `ready_for_training`.

## Known limitations / current status

- The login rate limiter is in-memory and per-process — fine for a
  single-worker deployment, but limits reset independently per worker in
  a multi-process deployment. Needs a shared store (Redis) before scaling
  workers horizontally.
- No automated tests for this module specifically, though Module 3's
  `test_client_runner_matches_simulation.py` exercises its data path, and
  `module3-fedlearning/seed_uci_heart.py` is an end-to-end exercise of
  the upload -> validate -> store path (dedicated unit tests are Sprint C).
- ~~`create_all` and Alembic both live during this transitional sprint~~ —
  **resolved in Sprint B**: `create_all` and `FEDHEAL_AUTO_CREATE_TABLES`
  are gone, `alembic upgrade head` is the only schema path now.
- ~~No `/health` endpoint~~ — **resolved in Sprint B**: added, same shape
  as Modules 2 and 7.
- Cross-machine verification of the real networked FL path
  (`client_runner.py` from genuinely separate machines) is still a
  stretch goal, not required for this sprint — see
  `docs/DEVELOPMENT_PLAN.md` section 4, item 6. Everything verified so far
  (`run_local_smoke_test.sh`, `test_client_runner_matches_simulation.py`)
  is localhost/subprocess-based, which is sufficient evidence the path
  itself is correct.

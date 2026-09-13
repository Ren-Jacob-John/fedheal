# Module 7 — Admin / Platform Module

## What this module is for

The platform operator's single view across the whole system: which
hospitals are active, is the shared model actually improving round over
round, and how much data is being flagged for quality issues — without
duplicating any other module's data. This module owns almost no data of
its own; it's a cross-cutting aggregation and proxy layer over Modules 1,
2, and 3.

## How it works internally

**Files:**
- `main.py` — the FastAPI app and all endpoints.
- `hospitals_client.py` — proxies hospital list/activate/deactivate calls
  through to Module 1 (the real source of truth for hospital data — this
  module never stores its own copy of hospital records).
- `models.py` — SQLAlchemy models for the data this module *does* own:
  `TrainingRound` (round history) and `ValidationFlag` (rolled-up
  flag/rejection counts).
- `schemas.py` — pydantic request/response schemas: `TrainingRoundIn/Out`,
  `ValidationFlagIn/Out`, `OverviewOut`.
- `auth.py` — token verification (shared `FEDMED_JWT_SECRET` with Module
  1 — this service only ever **verifies** tokens, never issues them) plus
  the per-caller service-key guards (`require_module2_service_key`,
  `require_module3_service_key`) that let Modules 2 and 3 report in
  without needing a user login.
- `database.py` — engine/session, same Postgres/Supabase-with-SQLite-
  fallback pattern as Module 1; can point at a separate database from
  Module 1 via `FEDHEAL_ADMIN_DATABASE_URL` if desired, or share the same
  project (different tables, no collisions).
- `seed_demo.py` — populates realistic demo data (hospitals, a few rounds
  of history, a mix of flags) for local development/demos.

**What's real vs. a documented prototype simplification (stated directly
in the module's own header comment, worth repeating here):**
- **Hospital list / activate-deactivate — real.** Proxies live to Module
  1, which is the actual source of truth.
- **Training-round history — real**, but depends on Module 3 actually
  reporting in. `simulate.py` posts here automatically after each round,
  best-effort (if this service is down, the simulation still runs fine
  standalone).
- **Validation-flag summaries — real**, same best-effort pattern from
  Module 2.
- **"Trigger a new federated round" — a real, working button** that
  currently launches Module 3's single-process `simulate.py` as a
  subprocess, not real separate hospital machines. That's an honest
  reflection of Module 3's own current stage, not a shortcut unique to
  this module — when Module 3 graduates to a real networked deployment,
  this endpoint's job stays the same (kick off training, receive the
  round-completion report back).

**Endpoints:**
- `GET /health` — liveness check.
- `GET /admin/hospitals`, `PATCH /admin/hospitals/{id}` — proxy to Module
  1.
- `POST /admin/rounds` (Module 3's service key) / `GET /admin/rounds` —
  record and list training-round history.
- `POST /admin/rounds/trigger` — kick off `simulate.py` as a subprocess.
- `POST /admin/flags` (Module 2's service key) / `GET /admin/flags` —
  record and list rolled-up validation flags.
- `GET /admin/overview` — the one-shot summary the dashboard's super-admin
  view is built on: hospital counts, latest round number/accuracy, total
  rounds recorded, total flags, flags in the last 7 days.

## How to run it

```bash
cd module7-admin
pip install -r requirements.txt
cp .env.example .env
python seed_demo.py    # optional — populate realistic demo data
uvicorn main:app --reload --port 8005
```

Interactive API docs: `http://localhost:8005/docs`

**Environment variables:** `FEDHEAL_DATABASE_URL` (or
`FEDHEAL_ADMIN_DATABASE_URL` for a separate project), `FEDMED_JWT_SECRET`
(must match Module 1's), `FEDHEAL_SVC_KEY_M2_M7` (must match Module 2's
caller value), `FEDHEAL_SVC_KEY_M3_M7` (must match Module 3's caller
value), `FEDMED_AUTH_API_URL` (where Module 1 is reachable).

## How it depends on / is depended on by other modules

- **Proxies to:** Module 1 (hospital data).
- **Receives best-effort reports from:** Module 2 (validation flags),
  Module 3 (round/accuracy history).
- **Triggers:** Module 3's `simulate.py` as a subprocess.
- **Called by:** Module 4's super-admin views (overview, rounds).

## Known limitations / current status

- "Trigger round" launches the single-process simulation, not real
  networked hospitals — an accurate reflection of where Module 3 is
  today, not a gap specific to this module.
- No automated tests yet.
- Service-to-service auth relies on shared secret values matching exactly
  across `.env` files in each module — a real deployment should manage
  these through a secrets manager rather than manually-synced `.env`
  files.

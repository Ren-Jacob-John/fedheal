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
- `models.py` — dataclasses (stored as Firestore documents) for the data this module
  *does* own: `TrainingRound` (round history), `ValidationFlag` (rolled-up
  flag/rejection counts), `RetrainingRequest` (count-only queue) and
  `ModelVersion` (the model registry).
- `repo.py` / `docstore.py` — all reads and writes / the Firestore + local-store backends
  (`docstore.py` is shared verbatim with Module 1). `migrate_from_sql.py` copies an old SQL database over.
- `schemas.py` — pydantic request/response schemas: `TrainingRoundIn/Out`,
  `RetrainingRequestOut`, `ValidationFlagIn/Out`, `OverviewOut`.
- `auth.py` — token verification (shared `FEDMED_JWT_SECRET` with Module
  1 — this service only ever **verifies** tokens, never issues them) plus
  the per-caller service-key guards (`require_module2_service_key`,
  `require_module3_service_key`) that let Modules 2 and 3 report in
  without needing a user login.
- `database.py` — picks the backend exactly like Module 1 (`FEDHEAL_DB_BACKEND`; Firestore in
  staging/production, a local JSON file in development). Can use a named Firestore database of
  its own via `FEDHEAL_ADMIN_FIRESTORE_DATABASE`, or share Module 1's (different collections,
  no collisions).
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
- **Retraining requests — gated and durable.** When enabled, Module 3
  runners report only their count of eligible, labeled, passed records.
  Module 7 establishes an initial per-hospital count baseline, then persists
  one request per N new eligible records since the last completed run. Only
  one pending/claimed request can exist per hospital at a time. The threshold
  defaults to disabled.

**Endpoints:**
- `GET /health` — liveness check.
- `GET /admin/hospitals`, `PATCH /admin/hospitals/{id}` — proxy to Module
  1.
- `POST /admin/rounds` (Module 3's service key) / `GET /admin/rounds` —
  record and list training-round history.
- `POST /admin/rounds/trigger?hospital_id=...` — return an already-queued
  request; it no longer starts a subprocess.
- `POST /admin/retraining/eligibility` — Module 3 runner, count-only; creates
  a request once `FEDHEAL_RETRAIN_MIN_ELIGIBLE_RECORDS` is met.
- `GET /admin/retraining/requests/next` and
  `POST /admin/retraining/requests/complete` — Module 3 runner, scoped to its
  token's hospital. A request can be marked `COMPLETED` only after Module 7
  links a registry candidate to it.
- `GET /admin/retraining/requests/{request_id}/candidate` — hospital-scoped
  runner status check; another hospital gets 404. Returns candidate id and
  lifecycle status only.
- `GET /admin/retraining/requests` — super_admin queue view.
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

**Environment variables:** `FEDHEAL_DB_BACKEND` / `FEDHEAL_FIREBASE_PROJECT_ID`
(`FEDHEAL_ADMIN_FIRESTORE_DATABASE` for a separate database), `FEDMED_JWT_SECRET`
(must match Module 1's), `FEDHEAL_SVC_SIGNING_KEY_M2_M7` (must match Module 2's
caller value), `FEDHEAL_SVC_SIGNING_KEY_M3_M7 and FEDHEAL_SVC_SIGNING_KEY_M8_M7` (must match Module 3's caller
value), `FEDHEAL_RETRAIN_MIN_ELIGIBLE_RECORDS` (unset/0 disables automatic
requests), `FEDMED_AUTH_API_URL` (where Module 1 is reachable).

Mint each hospital runner's queue token on the trusted operator host with
`python mint_retraining_runner_token.py --hospital-id <id>` and deliver only
the resulting token as `FEDHEAL_SVC_TOKEN_M3_M7` to that hospital.

## How it depends on / is depended on by other modules

- **Proxies to:** Module 1 (hospital data).
- **Receives best-effort reports from:** Module 2 (validation flags),
  Module 3 (round/accuracy history).
- **Coordinates:** Module 3's long-running `client_runner.py --watch-retraining`
  poller; the poller sends only the eligible-record count.
- **Called by:** Module 4's super-admin views (overview, rounds).

## Known limitations / current status

- Networked Flower runs register an aggregate candidate only when each
  participant supplies a unique claimed request id and the training counts
  attest that every example was validated and hospital-labeled. Missing or
  dirty provenance skips registration; queue completion then fails and does
  not advance the baseline.
- Candidate registration stores a CANDIDATE and links its id to participating
  queue requests atomically. It does not validate or promote the model.
  Validation remains a separate gate and promotion remains an explicit
  super_admin action. No cron scheduler is implemented.
- Service-to-service auth relies on shared secret values matching exactly
  across `.env` files in each module — a real deployment should manage
  these through a secrets manager rather than manually-synced `.env`
  files.

# Module 7 — Admin / Platform Module

Module 7 from the original proposal ("Admin/Platform Module — you, the
operator"), the cross-cutting piece that gives a platform operator one
screen across every other module. Where Modules 1–6 each look inward at
their own job (auth, one batch's validation, one federated round, one
prediction), this module looks *across* all of them — it's the operator's
one view for "how healthy is the whole platform right now."

It deliberately owns almost no data of its own. Hospital identity/status
belongs to Module 1; this module just asks Module 1 for it, live, every
time (see `hospitals_client.py`). The two things it *does* own are things
no other module has a home for yet: **training-round history** (Module 3
runs rounds but never persisted them anywhere) and **validation-flag
summaries** (Module 2 computes flags per-batch but never kept a log).

## What it does

- **Hospital oversight**: list every hospital and its active/inactive
  status, and flip that status — proxied straight through to Module 1,
  which is the real source of truth and enforces its own super_admin
  check too.
- **Training-round history**: every completed federated round (round
  number, hospital count, global accuracy, baseline accuracy) gets
  recorded here so "is the model actually improving?" has an answer
  beyond scrolling terminal output.
- **Trigger a new round**: a real endpoint that kicks off Module 3's
  `simulate.py` and lets it report its own progress back here.
- **Validation-flag visibility**: rolled-up counts+reasons of what Module
  2 rejected or flagged per hospital — never the underlying records, so
  this table structurally cannot contain patient data.
- **One overview endpoint** that a future dashboard "operator home
  screen" can call once and get everything above summarized.

## What's real vs. a prototype simplification (be upfront about both)

| Piece | Status |
|---|---|
| Hospital list / activate-deactivate | **Real.** Proxies live to Module 1's actual hospitals table. Required adding one new endpoint to Module 1: `PATCH /hospitals/{id}` (super_admin only). |
| Training-round history | **Real**, but only as good as who reports to it. `module3-fedlearning/simulate.py` now posts each round automatically (best-effort — the simulation still runs fine standalone if this service isn't up). |
| Validation-flag summaries | **Real**, same pattern — `module2-validation/main.py` now posts a rolled-up summary per batch call. |
| "Trigger round" button | **Real and working**, but it launches the *current* single-process `simulate.py`, not actual separate hospital machines — because that's the honest state of Module 3 right now too (see its README). When Module 3 grows real networked clients, this endpoint's job is unchanged: kick off training, let completion get reported back here. |
| Service-to-service auth | **Prototype-level.** Module 2/3 → here is gated by one shared secret header (`X-Service-Key`), not per-service credentials or mTLS. Fine for "only our own services can write this table" today; not what you'd ship with real hospital data. |

## Two kinds of caller, two kinds of credential

- **A human hitting `/admin/*` GET/PATCH endpoints** (an operator viewing
  the dashboard, activating a hospital, clicking "trigger round") needs a
  **super_admin JWT from Module 1** — this service verifies it, it never
  issues its own.
- **Another service posting data** (`POST /admin/rounds`,
  `POST /admin/flags`) isn't a logged-in person, so it uses the
  `X-Service-Key` header instead — Module 2 and Module 3 each have their
  OWN key (`FEDHEAL_SVC_KEY_M2_M7` / `FEDHEAL_SVC_KEY_M3_M7`) rather than
  one secret shared across every internal caller.

## Running it

```bash
cd module7-admin
pip install -r requirements.txt --break-system-packages

# MUST match the secret Module 1 was started with, or tokens won't verify here.
export FEDMED_JWT_SECRET=dev-only-change-me
export FEDHEAL_SVC_KEY_M2_M7=dev-only-key-module2-to-module7   # must match Module 2's
export FEDHEAL_SVC_KEY_M3_M7=dev-only-key-module3-to-module7   # must match Module 3's

uvicorn main:app --reload --port 8005
```

### Quick end-to-end check

```bash
# 1. Get a super_admin token from Module 1 (module1-auth must be running on :8001,
#    and you must have registered a user with role=super_admin — see its README).
TOKEN=$(curl -s -X POST http://localhost:8001/token \
  -d "username=admin@fedheal.dev&password=yourpassword" | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. See the operator overview
curl -s http://localhost:8005/admin/overview -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 3. Trigger a real federated round and watch it land
curl -s -X POST http://localhost:8005/admin/rounds/trigger -H "Authorization: Bearer $TOKEN"
sleep 5
curl -s http://localhost:8005/admin/rounds -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

No Module 1/2/3 running yet and just want to see the shape of the data?
`python seed_demo.py` populates rounds + flags directly into this
service's own SQLite DB.

## Using Supabase

Same pattern as `module1-auth` — `cp .env.example .env`, fill in your
Supabase connection string, `pip install -r requirements.txt`. By default
this reuses `module1-auth`'s `FEDHEAL_DATABASE_URL` (same Supabase
project, different tables — no naming collisions). Set
`FEDHEAL_ADMIN_DATABASE_URL` instead if you'd rather keep this module's
`training_rounds`/`validation_flags` tables in a separate project. Leave
both unset to fall back to local SQLite.

## Env vars

| Var | Default | Meaning |
|---|---|---|
| `FEDHEAL_DATABASE_URL` / `FEDHEAL_ADMIN_DATABASE_URL` | local SQLite | Supabase/Postgres connection string — see "Using Supabase" above |
| `FEDMED_JWT_SECRET` | `dev-only-change-me` | Must match Module 1's — this service only verifies tokens, never issues them. |
| `FEDHEAL_SVC_KEY_M2_M7` | `dev-only-key-module2-to-module7` | Module 2's own key for posting validation-flag summaries here. |
| `FEDHEAL_SVC_KEY_M3_M7` | `dev-only-key-module3-to-module7` | Module 3's own key for posting completed rounds here. |
| `FEDMED_AUTH_API_URL` | `http://localhost:8001` | Where Module 1 is reachable, for the hospital proxy calls. |

## Not done yet (next sprint)

- No pagination beyond a `limit` param — fine at prototype scale, not at
  real scale.
- The "trigger round" endpoint doesn't track *whether* the subprocess
  it started actually succeeded, only that it launched. A job-queue
  (Celery/RQ, same as Module 3's own planned graduation path) would fix
  this properly.
- No **standalone** admin app — the super_admin views (overview, rounds
  history, validation flags, trigger-round, hospital activate/deactivate)
  are already wired into `module4-dashboard-react` for `super_admin`
  users. What's still missing: Module 8 synthesis reports, SHAP/Grad-CAM
  chart rendering, and CSV upload (see `docs/16-week-development-plan.md`
  week 14).

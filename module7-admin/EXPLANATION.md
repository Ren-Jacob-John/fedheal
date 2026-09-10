# Module 7 — Admin / Platform Module: Full Explanation

## What this module is for

Modules 1–6 each look inward at their own job: authenticate a user,
validate one batch, run one federated round, make one prediction. Nobody
has a single screen showing "how healthy is the whole platform right
now?" — how many hospitals are active, is the shared model actually
improving round over round, how much data is getting flagged for quality
issues. This module is that screen's backend: the platform operator's
(the person running FedHeal across all participating hospitals) one place
to see across every other module at once.

## How it works

This module deliberately owns almost no data of its own. Hospital
identity and status belong to Module 1 — this module just asks Module 1
for it, live, on every request (`hospitals_client.py`), rather than
keeping its own stale copy. The two things it *does* own are things no
other module had a home for: a persisted log of **training-round
history** (Module 3 runs rounds but never saved a record of them anywhere
before this module existed) and a persisted log of **validation-flag
summaries** (Module 2 computes flags per batch but never kept history
across batches).

Two different trust boundaries are enforced here, deliberately kept
separate:

- **A human operator** hitting the `/admin/*` endpoints (viewing the
  overview, activating a hospital, clicking "trigger round") needs a
  `super_admin` JWT — the exact same JWT Module 1 issues. This service
  only *verifies* that token; it never issues its own, because there's
  meant to be exactly one login system in the whole platform.
- **Another service posting data** (Module 2 reporting a validation-flag
  summary, Module 3 reporting a completed round) isn't a logged-in human,
  so it authenticates with a much simpler shared-secret header
  (`X-Service-Key`) instead.

## What it actually does

- **Hospital oversight** — list every hospital and its active/inactive
  status, and flip that status. This is a real, working proxy straight
  through to Module 1 (which required adding one new endpoint there,
  `PATCH /hospitals/{id}`, restricted to `super_admin`).
- **Training-round history** — every completed federated round (round
  number, hospital count, global accuracy, baseline accuracy) gets
  recorded here, so "is the model actually improving?" has a real answer
  instead of requiring someone to scroll back through terminal output.
- **Trigger a new round** — a working endpoint that launches Module 3's
  training script as a background process and lets it report its own
  progress back here as each round completes.
- **Validation-flag visibility** — rolled-up counts and reasons of what
  Module 2 rejected or flagged, broken down per hospital. Never the
  underlying patient-adjacent records — only a tally like "3 records
  rejected for out-of-range height" — so this table structurally cannot
  contain patient data even by accident.
- **One overview endpoint** that bundles all of the above into a single
  call, built for exactly what an operator's dashboard home screen wants.

## How other modules depend on it

- **Module 1** provides the hospital data this module proxies, and
  received a new endpoint (`PATCH /hospitals/{id}`) specifically to support
  this module's activate/deactivate feature.
- **Module 2** posts a rolled-up validation-flag summary here after every
  batch it validates — best-effort, so validation keeps working perfectly
  even if this service is down.
- **Module 3** posts a summary after every completed federated round, same
  best-effort pattern.

## What's real vs. what's a known prototype simplification

Real: the hospital proxy, the training-round and validation-flag logging,
the trigger-round endpoint, the two-tier auth model, and per-caller
service credentials — Module 2 and Module 3 each authenticate with their
own key (`FEDHEAL_SVC_KEY_M2_M7` / `FEDHEAL_SVC_KEY_M3_M7`) rather than
one secret shared across every internal caller. Still a placeholder for
real service auth (mTLS, or keys issued by an internal secrets manager) —
fine for "only our own services can write this table" at prototype
stage, not what you'd ship against real hospital data. Documented in this
folder's `README.md`: the "trigger round" endpoint knows a training
process *launched* but not whether it actually *succeeded* (a real job
queue like Celery/RQ would fix this properly, matching Module 3's own
planned graduation path); the super_admin slice of Module 4's React
dashboard already consumes this API (overview, rounds, flags, trigger-
round, hospital status) — what's still missing is Module 8 synthesis
rendering and explainer charts (see week 14 in
`docs/16-week-development-plan.md`).

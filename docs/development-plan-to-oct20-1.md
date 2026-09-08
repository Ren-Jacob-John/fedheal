# FedHeal — Updated Development Plan (target: Oct 20, 2026)

**Written:** Sep 3, 2026. **Deadline:** Oct 20, 2026 — **47 days / 6.7 weeks
from today.**

## Where the project actually stands (verified against the live repo, not just the docs)

I cloned `github.com/Ren-Jacob-John/fedheal` and checked the real commit
history rather than taking the existing `docs/16-week-development-plan.md`
at face value. Two things worth knowing before trusting any schedule:

- **Real elapsed time so far is ~3 weeks of active work, not 9.** First
  commit was **Jul 23**; the 8-module scaffold + first integration pass
  landed by **Aug 10**. Then there's a **three-week gap with zero commits
  (Aug 10 → Sep 2)**. Yesterday and today (Sep 2–3) saw a burst of activity
  (Supabase wiring, README/docs updates, UI work). So the team's actual
  working velocity is faster than the old plan's "week 9" framing suggests
  — worth knowing, because it means the Oct 20 target is tight but not
  unreasonable *if the team commits steadily instead of bursting*.
- **The zip you uploaded matches the live repo exactly** (I diffed them —
  no differences outside `.git`/`__pycache__`/the local sqlite file). So
  everything below is based on what's actually on `main` right now, not a
  stale snapshot. One inconsistency to flag: the live `README.md` refers
  to `module4-dashboard-react/` as if the plain-HTML dashboard was already
  replaced and removed — but the actual folder is still `module4-dashboard/`,
  and it already **is** a React+Vite app (has `.jsx`, `vite.config.js`,
  etc.). The code is fine; the README just describes a rename that never
  happened. Worth a 5-minute fix (either rename the folder or fix the
  prose) so docs and reality agree — I've included it below.

Modules 1–8 exist, run standalone, and are wired together for one real
data path (upload → validate → store → train). That's genuinely solid
groundwork. The gaps are the ones the project's own module READMEs
already admit to in their "Next sprint" sections — nothing below is a
surprise to the team, it just hasn't been scheduled against a real date
until now.

## Scope decisions for a 6.7-week runway

The original plan's weeks 10–16 assumed a fuller runway and included some
genuinely heavy lifts (real networked FL across machines with TLS, a full
imaging suite across 5+ specialists, four SOTA foundation models that
need GPU + Hugging Face access neither of which this environment has).
Trying to do all of it in 6.7 weeks risks finishing none of it well. I'm
proposing explicit cuts so the team is choosing what to drop on purpose,
not discovering it on Oct 18:

| Keep (must-have for Oct 20) | Cut / defer past Oct 20 |
|---|---|
| Real diagnosis/outcome labels replacing the placeholder | Alembic migrations (SQLite/`create_all` is fine for a demo) |
| **One** imaging specialist trained real end-to-end (recommend retina/APTOS — smallest, cleanest dataset) | The other 4 imaging specialists' real fine-tuning — stay on documented stub fallback |
| Real federated learning across separate local processes (gRPC, `server.py` + a `client_runner.py`) | TLS/production-grade multi-host security for that FL traffic |
| CSV upload + flagged-record human review in the dashboard | RadFM / BiomedParse / SegVol / OmiCLIP going from stub to real (needs GPU + HF access the team should confirm it even has) |
| Security essentials: CORS lockdown, `/token` rate limiting, real per-service credentials, httpOnly token storage | Full production secrets management |
| Docker Compose for one-command local full-stack demo + a lint/test CI check | Formal IRB process (write-up only, not the actual process — that's outside a 6-week window regardless) |
| End-to-end integration test across the real module boundaries | Extensive test coverage beyond the critical path |

If the team disagrees with any of these cuts, swap them — the point is
that every week below is scoped to what's realistically finishable, not
padded with items that quietly won't happen.

## Week-by-week schedule

Owners follow the existing `README.md` table: **P1** = Backend/Auth,
**P2** = Data Engineer, **P3** = ML Engineer, **P4** = Frontend.

| Sprint | Dates | Focus | Owner(s) | Deliverables | Status |
|---|---|---|---|---|---|
| 1 | Sep 3 – Sep 9 | **Real labels + doc/repo cleanup** | P1 + P2 | Add a real diagnosis/outcome field to the vitals upload schema and dashboard form; retire `real_data.py`'s rule-based placeholder; fix the `module4-dashboard` vs. `module4-dashboard-react` naming mismatch (rename or correct the README — pick one and be consistent everywhere docs reference it) | ✅ Done — `label` wired through Module 1/2/3 end-to-end, dashboard upload form has a label field, folder is `module4-dashboard-react` matching README. **Note:** `real_data.py`'s placeholder is still in the code as a *fallback* for records with no label — that's correct (some demo/legacy records still won't have one), not a leftover to remove. |
| 2 | Sep 10 – Sep 16 | **CSV upload + flagged-record review** | P2 + P4 | Module 2 accepts `UploadFile` CSV, not just JSON; dashboard UI lets a hospital admin see and approve/reject `flagged` records instead of them being silently dropped | ✅ Done — `POST /validate/vitals/csv` exists; `FlaggedReview.jsx` gives admins approve/reject on flagged records. Completed early, in parallel with sprint 1. |
| 3 | Sep 17 – Sep 23 | **Real networked FL, part 1** | P3 (+ P1 for infra) | Stand up `server.py` for real; write `client_runner.py` that a separate process/machine actually runs via `fl.client.start_client`; get 2 "hospital" processes federating over localhost gRPC | ✅ Done Sep 7, **10 days early** — `client_runner.py` written and verified live: real Module 1 instance, 2 hospitals seeded with distinct (non-IID) data, real `server.py` gRPC server, 2 separate `client_runner.py` **processes** (one addressed by `--hospital-id`, one by `--hospital-name`) completed 8 real federated rounds, `aggregate_fit: received 2 results and 0 failures` every round. |
| 4 | Sep 24 – Sep 30 → **moved up to Sep 8 – Sep 14** | **Real networked FL, part 2 + imaging kickoff** | P3 | Extend to 3+ real clients, confirm results match `simulate_real.py`'s numbers (sanity check the new path against the known-good one); in parallel, start the retina/APTOS fine-tune (imaging training runs take real wall-clock time — start it now so it isn't a week-8 surprise) | ⬜ Not started — see rebaselined plan below |
| 5 | Oct 1 – Oct 7 | **Imaging finishes + security hardening** | P3 + P1 | Finish and validate the real retina specialist end-to-end through Module 5's router/fusion; CORS lockdown to the real dashboard origin, `/token` rate limiting, per-service credentials replacing the shared `X-Service-Key`, httpOnly cookie token storage | 🟨 Partially done early — CORS lockdown, `/token` rate limiting, per-service credentials (not one shared key), and httpOnly cookie tokens are already in Module 1's `main.py`/`auth.py`. Retina fine-tune still not started (blocks this sprint's remaining scope). |
| 6 | Oct 8 – Oct 14 | **Integration testing + Docker Compose** | Whole team | End-to-end test covering login → upload → validate → federated round → prediction → synthesis packet; `Dockerfile` per service + one `docker-compose.yml` bringing up the full stack locally; basic CI (lint + test on push) | ⬜ Not started |
| 7 | Oct 15 – Oct 20 | **Bug-fix pass + demo prep** | Whole team | Fix whatever sprint 6 testing surfaced; a scripted demo run showing federated accuracy beating the local-only baseline on real (not synthetic) data; short compliance write-up (what HIPAA/GDPR/IRB would require for real deployment — documented, not executed); final report + slides | ⬜ Not started |

**Re-baseline note (Sep 7):** actual velocity is running ~10 days ahead of
the Sep 3 schedule — sprints 1–3 are functionally complete a week and a
half early, and part of sprint 5 (security) got pulled forward too. Rather
than let the team coast until the calendar catches up (the exact "burst,
then a 3-week gap" pattern this plan's intro already flagged once), the
schedule below pulls sprint 4 forward to start now instead of Sep 24. If
this pace holds, Oct 20 stops being "tight but not unreasonable" and
becomes genuine buffer — but one strong week proves a pace, not a trend,
so sprints 5–7's dates are left where they were rather than compressed too.

That's 6 full sprints of build + 1 final sprint (only 6 days — Oct 15 is
a Thursday) that's fix-and-polish only, deliberately, because "testing
week" and "polish week" being the same week is how projects ship broken
demos.

## Next sprint (rebaselined): Sep 8 – Sep 14 — FL hardening + imaging kickoff

Sprint 3's core deliverable (2 real networked clients) is done and
verified. This sprint is what was scoped as sprint 4, started 16 days
early, plus the small hardening items sprint 3 surfaced once it was
actually run end-to-end rather than just written.

**Owner:** P3 (+ P1 for infra on the imaging training environment)

| # | Task | Why | Acceptance check |
|---|---|---|---|
| 1 | Extend to 3+ real `client_runner.py` processes against the same `server.py` | Sprint 4's stated goal — a 3rd real client is a stronger demo than 2, and `server.py`'s `FedAvg(fraction_fit=1.0, ...)` already uses however many clients connect, so this needs zero code changes, just running it | 3 (or more) real hospital processes complete all 8 rounds together; server log shows `received 3 results and 0 failures` |
| 2 | Sanity-check `client_runner.py`'s results against `simulate_real.py`'s | The whole point of building the real networked path is that it should reach the *same conclusion* as the known-good in-process one — if it doesn't, something in the new path (data loading, serialization, round timing) is silently wrong | Seed identical hospital data for both; final global-model accuracy on the same holdout is within a few points of each other. Worth turning into `test_client_runner_matches_simulation.py` now rather than a one-off manual check, since sprint 6 needs an integration test anyway |
| 3 | Make `min_fit_clients` / `min_available_clients` configurable on `server.py` (currently hardcoded to 2) | Minor, but running with only 2 of 3 clients connected should be a deliberate choice (`--min-clients`), not just whatever the hardcoded default happens to allow | `python server.py --min-clients 3` refuses to start a round until 3 are connected |
| 4 | Fix `server.py`'s stale docstring ("once `client_runner.py` exists") | It exists now — a one-line fix, but the kind of small doc drift that compounds if left | Docstring reads correctly for a teammate encountering it fresh |
| 5 | Turn today's manual smoke test into `run_local_smoke_test.sh` (start Module 1 + `server.py` + N clients, seed test data, assert the run completes, tear everything down) | So "does real FL still work" is a 30-second scripted check for the rest of the team, not a multi-terminal manual walkthrough only I've done | One command, non-zero exit on failure, clean process teardown either way |
| 6 | **Kick off** the retina/APTOS fine-tune | Training has real wall-clock time that doesn't compress — starting now (not Sep 24, and not waiting on task 1–5) is what avoids the week-8 surprise the original plan called out | `train_retina.py` exists, runs against a real APTOS download, and produces a checkpoint `imaging_retina.py` can load — doesn't need to be *finished* this sprint, just genuinely started with real data, not another stub |

**Task 6 needs an environment this sandbox doesn't have.** `module5-modelzoo/requirements.txt`
already documents why torch/torchvision aren't installed here ("disk-constrained... install
on a real dev machine or training server"), and `imaging_retina.py` currently builds
`resnet50(weights=None)` — random init, no checkpoint loading path at all yet. Concretely,
task 6 means: (a) get the APTOS 2019 dataset, (b) write `train_retina.py` (standard
transfer-learning loop: load ImageNet weights, fine-tune the unfrozen `fc` layer per
`imaging_retina.py`'s existing `freeze_backbone=True` split, save a checkpoint), (c) add
checkpoint loading to `ResNet50RetinaModel.__init__` so `weights=None` becomes "load our
fine-tuned weights if present, else fall back to the documented stub." P1 should confirm
which machine/GPU this actually runs on before P3's week is blocked waiting for one.

**Definition of done for this sprint:** 3+ real hospitals federating (not
2), a scripted way to re-verify that stays true, and the retina fine-tune
underway with real data — even if not yet complete — so sprint 5 opens
with "finish and validate" rather than "start."

## Sequencing logic

- **Labels first (sprint 1).** Every module README that mentions the
  placeholder label calls it "the actual next blocker, not a nice-to-have"
  — federated accuracy numbers are meaningless until this is real, so
  nothing downstream (imaging validation, FL comparison numbers, the
  final demo's headline claim) can be trusted before it's fixed.
- **Real FL before imaging finishes, but imaging *starts* in parallel
  (sprint 4).** Networked FL is architecturally risky (new failure modes:
  network, serialization, timing) so it gets focused time alone in sprint
  3. But model fine-tuning has unavoidable wall-clock training time that
  doesn't compress just because you assign more people to it — so it
  starts the moment sprint 3's FL work is stable enough to not need full
  attention, rather than waiting until security/testing weeks are done.
- **Security and testing are their own sprints, not "and also" items.**
  Exactly the same reasoning the original 16-week plan used, and exactly
  the failure mode to avoid on a compressed timeline: things without a
  dedicated slot are the first things silently dropped when a sprint runs
  long.
- **The last sprint is 6 days and fix-only on purpose.** No new features
  land in sprint 7. If sprint 6 finishes early, that time moves *forward*
  into sprint 7 as buffer, not backward into adding more scope to sprints
  1–6.

## Risk / what to cut first if a sprint slips

In priority order, if the team falls behind:

1. Drop the retina imaging fine-tune first — it's valuable but the
   project's core value proposition (federated learning beating
   local-only training) does not depend on it. Fall back to the existing
   stub, which is honestly documented already.
2. Drop the 3rd+ real FL client — 2 real networked clients is enough to
   prove the architecture works; more clients is a stronger demo, not a
   different demo.
3. Drop Docker Compose in favor of the existing per-module `README.md`
   run commands — less polished, but doesn't block the demo.
4. Do **not** cut sprint 1 (real labels) or sprint 7 (buffer) under any
   circumstance — the first invalidates every accuracy number the demo
   would show, the second is what keeps a late slip from becoming a
   missed deadline.

## Definition of done for Oct 20

- A live demo where a federated round trained on **real, labeled hospital
  data** (not synthetic, not placeholder-labeled) shows the federated
  model beating at least one hospital's local-only baseline.
- That training happens over **actual networked FL clients**, not the
  in-process simulation.
- At least **one** imaging specialist is real end-to-end, not stubbed.
- The dashboard supports CSV upload and a human can review flagged
  records, not just see a rolled-up count.
- The stack starts with one command (`docker-compose up`) and passes a
  basic CI check.
- A short, honest compliance write-up exists — it should read like the
  rest of this project's docs (plainly stating what's real vs. what
  would still be required for actual hospital deployment), not oversell
  readiness.

# FedHeal — 16-Week Development Plan

This maps the project from initial proposal to a finished, presentable
build. Weeks 1–9 describe work that's **already done** (the modules in
this repo, plus this sprint's data-flow integration) restated as a
week-by-week history, so the plan reads as one continuous timeline rather
than "here's what happened, here's what's next" as two disconnected
documents. Weeks 10–16 are the forward plan.

Team roles carry over from the existing `README.md` team-assignment table:
**P1** = Backend/Auth, **P2** = Data Engineer, **P3** = ML Engineer,
**P4** = Frontend. Adjust names/counts to your actual team size — the
module boundaries were deliberately drawn so 1–4 people can each own a
clear slice without blocking each other.

| Week | Focus | Module(s) | Owner | Key deliverables | Status |
|---|---|---|---|---|---|
| 1 | Requirements & architecture | — | Whole team | Problem statement, dataset shortlist (MIMIC-III/IV, UCI Heart Disease, NIH ChestX-ray14, ISIC, APTOS 2019), tech-stack decisions (Python/FastAPI/Flower/PyTorch/XGBoost), repo scaffolding, `docs/model-algorithm-catalog.md` | ✅ Done |
| 2 | Authentication & multi-tenancy | Module 1 | P1 | Hospital/user models, JWT login, hospital-scoped `get_current_user` pattern every later module follows | ✅ Done |
| 3 | Data ingestion & validation | Module 2 | P2 | De-identification screen, schema/range/consistency checks, isolation-forest outlier flagging | ✅ Done |
| 4 | Local training + FedAvg core | Module 3 | P3 | `HospitalClient`, manual FedAvg loop (`simulate.py`) proving federation beats a local-only baseline on synthetic non-IID data | ✅ Done |
| 5 | Hospital dashboard v0 | Module 4 | P4 | Plain HTML/JS login + status view wired to Module 1's real API (no framework yet, on purpose — API was still moving) | ✅ Done |
| 6 | Model zoo & task router | Module 5 | P3 | `SpecialistModel` interface, XGBoost (real) + DenseNet201/ResNet50/EfficientNet/U-Net (real code, auto-stubbed without torch), metadata router, fusion layer | ✅ Done |
| 7 | Condition router & explainability | Module 6 | P3 | Disease-name → specialist(s) + reasoning-method auto-switch; SHAP, Grad-CAM, and a rule-based knowledge-graph reasoner wired to real predictions | ✅ Done |
| 8 | Admin / platform module | Module 7 | P1 | Cross-module operator view: hospital oversight (proxies Module 1), training-round history, validation-flag summaries, "trigger a round" endpoint | ✅ Done |
| 9 | **Data-flow integration** | Modules 1, 3, 4 | P1 + P3 + P4 | Real pipeline: dashboard upload → Module 1 → Module 2 validation → stored per-hospital → `simulate_real.py` trains on it instead of synthetic data; `/training-status` becomes DB-backed | ✅ Done (this sprint) |
| 10 | Real datasets & labels | Modules 2, 3 | P2 + P3 | Swap the structured-data track onto UCI Heart Disease / MIMIC-derived features; add a real diagnosis/outcome field to the vitals schema and upload flow, retiring `real_data.py`'s placeholder label | ⬜ Planned |
| 11 | Imaging track goes live | Module 5 | P3 | Install torch/torchvision for real; fine-tune ResNet50 on APTOS 2019 (retinal) on at least one real specialist end-to-end; begin a ChestX-ray14 subset for DenseNet201 | ⬜ Planned |
| 12 | Real networked federated learning | Module 3 | P3 + P1 | Stand up `server.py` for real; write `client_runner.py` a "hospital" machine actually runs (`fl.client.start_numpy_client`) over gRPC/TLS, replacing `simulate_real.py`'s in-process loop | ⬜ Planned |
| 13 | Security & infra hardening | Modules 1, 2, 7 | P1 | ~~Postgres migration~~ (Supabase wired in early — see below); Alembic migrations, real per-service credentials replacing the shared `X-Service-Key`, CORS lockdown, `/token` rate limiting, httpOnly-cookie token storage instead of `localStorage` | ⬜ Planned (partially pulled forward) |
| 14 | Frontend rebuild | Module 4 (+ new admin UI) | P4 | React/Next.js hospital dashboard; CSV upload (not just pasted JSON); Grad-CAM heatmap overlays and SHAP charts rendered from Module 6's real explainer output; an admin screen consuming Module 7's `/admin/overview` | ⬜ Planned |
| 15 | Testing, QA & deployment | All | Whole team | End-to-end integration tests across every module boundary; Dockerfile per service + one `docker-compose.yml` for full-stack local deploy; CI (lint + test on push); IRB/HIPAA/GDPR compliance write-up per the proposal's "real deployment" section | ⬜ Planned |
| 16 | Polish, demo & submission | All | Whole team | Bug-fix pass from week 15's testing; final run showing federated accuracy beating the local-only baseline on real data; demo script/video; final report and presentation slides | ⬜ Planned |

## Why this ordering

- **Riskiest technical piece first.** FedAvg (week 4) started on synthetic
  data in isolation before anything depended on it, so a fundamental
  federated-learning bug would surface in week 4, not week 12.
- **Wiring only after every piece exists.** Modules 1–7 (weeks 2–8) were
  each built and smoke-tested standalone; week 9 is where the first real
  cross-module data flow landed, once there was something real on both
  ends of every wire.
- **Real data before real networking.** Week 10 (real datasets/labels) and
  11 (real imaging) come before week 12 (real networked FL) — there's no
  point building real gRPC transport for hospitals to federate on
  placeholder labels and synthetic images.
- **Hardening and polish are their own weeks, not squeezed into feature
  weeks.** Security (13), frontend (14), and testing/deployment (15) each
  get a dedicated week rather than being "and also" items tacked onto
  feature work, because they're exactly the things that get cut when
  they're not scheduled explicitly.

## Note on Supabase

Modules 1 and 7's Postgres migration (originally scheduled for week 13)
was pulled forward and wired up early, using Supabase as the managed
Postgres provider — both services now read `FEDHEAL_DATABASE_URL` and
fall back to local SQLite if it's unset, so nothing about local dev
workflow changed. See `module1-auth/README.md`'s "Using Supabase" section
for setup. Alembic migrations are still week 13 work — table creation is
still "create if not exists," not a real migration story.

## Known gaps this plan is honest about

- Every "done" module documents its own stubs/placeholders in its
  `README.md`'s "Next sprint" section — e.g., Module 5's imaging
  specialists auto-stub without torch installed, Module 6's genomic
  models fit on synthetic gene panels, Module 3's federated labels are a
  rule-based placeholder until week 10. This plan schedules the fixes;
  it doesn't pretend they're already fixed.
- 16 weeks does not reach the proposal's full "real hospital deployment"
  bar (IRB approval, per-hospital data-governance agreements, production
  secrets management) — week 15's compliance write-up documents what
  *would* be required, it doesn't complete that process, which is outside
  a single team's control on this timeline.

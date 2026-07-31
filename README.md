# FedHeal — Federated Learning Healthcare AI

Starter codebase for the first development milestone, split across a 4-person team
following the build order from the project proposal:

1. Auth + multi-tenancy (get hospital logins working)
2. Data ingestion + validation (structured-data track)
3. Local training (XGBoost/logistic regression) + Flower federated loop across simulated hospitals
4. Dashboard wired to show login + training/round status

## Documentation map

- **`docs/16-week-development-plan.md`** — the full 16-week schedule this
  project follows, from initial proposal through final demo. Weeks 1–9
  cover the modules already in this repo; weeks 10–16 are the forward plan.
- **Every `moduleN-*/EXPLANATION.md`** — a full, presentation-ready
  explanation of what that module does, how it works, and how it connects
  to the rest of the system. (`moduleN-*/README.md` stays the terse,
  dev-facing "how to run this" reference — the two are meant to be read
  together, not as duplicates.)

## Model / algorithm / framework catalog

**Read `docs/model-algorithm-catalog.md` before building any new disease
specialist.** It covers every model family, algorithm, and framework
relevant to medical diagnosis + reasoning — imaging (2D classification,
segmentation, whole-slide/histopathology), tabular/EHR, genomic/omics,
clinical NLP, time-series, survival analysis, multi-modal fusion, and
explainability/reasoning methods (Grad-CAM, SHAP, causal inference,
knowledge graphs, etc.) — not just the five models currently implemented
in `module5-modelzoo`. Disease-specific notes for breast cancer and
leukemia are included, plus a general pattern for any disease not yet
named. Every future stage should pick its model(s) from this document.

## Team assignment

| Person | Module | Folder | Status this sprint |
|---|---|---|---|
| **P1 — Backend/Auth** | Authentication & Multi-Tenancy | `module1-auth/` | ✅ Done & tested. Hospital register/login/JWT, hospital-scoped endpoints. |
| **P2 — Data Engineer** | Data Ingestion & Validation | `module2-validation/` | ✅ Done & tested. Schema, range, consistency, and outlier checks. |
| **P3 — ML Engineer** | Local Training + Federated Aggregation | `module3-fedlearning/` | ✅ Done & tested. Working FedAvg simulation, 3 hospitals, non-IID data. |
| **P4 — Frontend** | Hospital Dashboard | `module4-dashboard/` | ✅ Done & tested. Plain HTML/JS wired to Module 1's real API. |
| **P3 (cont.) — ML Engineer** | Model Zoo & Task Router | `module5-modelzoo/` | ✅ Done & tested. XGBoost (real) + DenseNet201/ResNet50/EfficientNet/U-Net (real code, stubbed in this sandbox — see its README) coexisting via a router + fusion layer. |
| **P3 (cont.) — ML Engineer** | Condition Router (auto-switch by disease) | `module6-condition-router/` | ✅ Done & tested. Mention a disease (breast cancer, leukemia, diabetic retinopathy, etc.) and it auto-routes to the right specialist(s) + reasoning method(s) — see its README for the 5 verified condition pathways. |
| **P1 (cont.) — Backend/Auth** | Admin / Platform Module (the operator's view) | `module7-admin/` | ✅ Done & tested. Hospital oversight (proxies Module 1), training-round history, validation-flag summaries, and a working "trigger a round" endpoint. First real cross-module wiring — see its README for exactly what's real. |

> Week mapping for this build: Week 1 = Modules 1–4, Week 2 = Module 5,
> Week 3 = Module 6, Week 4 = Module 7. This is the 8-module breakdown
> from the original proposal, not a 16-stage syllabus — if your
> course/team has a specific 16-stage breakdown, share it and this
> numbering can be remapped to match.

Every module runs and was smoke-tested independently. Modules 1–6 were
**not wired to each other** on purpose in earlier sprints — Module 7
brought the first real integration (dashboard status, training rounds,
validation flags), and **this sprint wires the actual data flow**: Module 1
now has a real `POST /vitals/upload` (forwards to Module 2 for validation,
stores passed/flagged records per hospital) and `GET /vitals/export`
(service-key gated, for Module 3), `training-status` is DB-backed instead
of a fake dict, the dashboard has a real upload form, and
`module3-fedlearning/simulate_real.py` runs FedAvg over that real,
validated hospital data instead of synthetic partitions. The one honest
gap left: uploaded vitals don't yet carry a real diagnosis/outcome label,
so `real_data.py` falls back to a rule-based placeholder — see its
docstring before treating any accuracy number from `simulate_real.py` as
clinically meaningful.

Each folder is independently runnable so the four of you aren't blocked on each other
this sprint. Module 3's `simulate.py` still doesn't depend on Module 1/2 — it uses
synthetic data so ML work can start immediately without a live pipeline; use
`simulate_real.py` once you want to exercise the real, wired-up path.

## Why this order

- Module 3 (FedAvg loop) is the riskiest/most novel piece technically, so it starts now,
  in isolation, on synthetic data — nobody wants to discover in week 4 that the
  federated averaging logic doesn't work.
- Module 1 and 2 can be built in parallel; neither depends on the other.
- Module 4 just needs Module 1's API contract (see `module1-auth/README.md`) to start
  wiring real requests instead of mocked ones.

## Running things

Each module has its own README with exact setup commands. Quick summary:

```bash
# Module 1 — Auth API
cd module1-auth && pip install -r requirements.txt --break-system-packages
uvicorn main:app --reload --port 8001

# Module 2 — Validation service
cd module2-validation && pip install -r requirements.txt --break-system-packages
uvicorn main:app --reload --port 8002

# Module 3 — Federated learning simulation
cd module3-fedlearning && pip install -r requirements.txt --break-system-packages
python simulate.py          # synthetic data, no dependencies on other modules
python simulate_real.py     # real hospital data — needs Module 1 + Module 2 running first

# Module 4 — Dashboard (no build step, just open it)
cd module4-dashboard && python -m http.server 8080
# then open http://localhost:8080

# Module 7 — Admin/Platform service (start Module 1 first — it proxies to it)
cd module7-admin && pip install -r requirements.txt --break-system-packages
export FEDMED_JWT_SECRET=dev-only-change-me   # MUST match Module 1's
export FEDMED_SERVICE_KEY=dev-only-internal-service-key
uvicorn main:app --reload --port 8005
```

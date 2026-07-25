# FedMed — Federated Diagnostic Support Platform

Starter codebase for the first development milestone, split across a 4-person team
following the build order from the project proposal:

1. Auth + multi-tenancy (get hospital logins working)
2. Data ingestion + validation (structured-data track)
3. Local training (XGBoost/logistic regression) + Flower federated loop across simulated hospitals
4. Dashboard wired to show login + training/round status

## Team assignment

| Person | Module | Folder | Status this sprint |
|---|---|---|---|
| **P1 — Backend/Auth** | Authentication & Multi-Tenancy | `module1-auth/` | ✅ Done & tested. Hospital register/login/JWT, hospital-scoped endpoints. |
| **P2 — Data Engineer** | Data Ingestion & Validation | `module2-validation/` | ✅ Done & tested. Schema, range, consistency, and outlier checks. |
| **P3 — ML Engineer** | Local Training + Federated Aggregation | `module3-fedlearning/` | ✅ Done & tested. Working FedAvg simulation, 3 hospitals, non-IID data. |
| **P4 — Frontend** | Hospital Dashboard | `module4-dashboard/` | ✅ Done & tested. Plain HTML/JS wired to Module 1's real API. |

Every module runs and was smoke-tested independently. They are **not yet
wired to each other** on purpose — that's next sprint's integration work
(see each module's README for exactly what's still a stub/placeholder).

Each folder is independently runnable so the four of you aren't blocked on each other
this sprint. Module 3 doesn't depend on Module 1/2 yet — it uses synthetic data so ML
work can start immediately. Wire them together (real data flowing from validation →
training, real JWTs gating the dashboard) in the *next* sprint.

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
python simulate.py

# Module 4 — Dashboard (no build step, just open it)
cd module4-dashboard && python -m http.server 8080
# then open http://localhost:8080
```

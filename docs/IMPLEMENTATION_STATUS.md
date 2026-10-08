# FedHeal — Implementation Status (baseline audit)

Audit date: 2026-10-06. Scope: inspection only. **No application code was changed.**
Everything below was read from the repository or observed by running it; items I
could not verify are marked **UNVERIFIED**. No clinical metrics are claimed anywhere
in this document.

Legend: **IMPLEMENTED** (works, tested) · **PARTIAL** (works with gaps) · **STUB**
(placeholder that labels itself as such) · **BROKEN** · **MISSING**.

---

## 1. Architecture overview

Eight cooperating modules. Python 3.12 / FastAPI services, one React (Vite) dashboard,
one Flower (flwr) federated-learning layer. One login system (Module 1 JWT); services
call each other with hop-specific signed service tokens.

```
Browser (M4 React) ──cookie/Bearer JWT──► M1 auth/vitals  :8001 ──svc token M1→M2──► M2 validation :8002
        │                                   ▲  ▲                                          │ svc key M2→M7
        │                                   │  └── scoped svc token M3→M1 (/vitals/export)│
        ├──JWT──► M7 admin :8005 ◄──svc key M3→M7── M3 FL (Flower server :8080 / client_runner)
        └──JWT──► M8 synthesis :8006 ──user's own JWT──► M1 (reads stored record)
                       └─ imports M6 condition-router ─► imports M5 model zoo (in-process, via sys.path)
```

| Layer | Where |
|---|---|
| Backend APIs | M1, M2, M7, M8 (FastAPI + uvicorn) |
| Frontend | M4 (React 18 + Vite 8, no UI framework) |
| Database | SQLAlchemy 2. M1 + M7 share `FEDHEAL_DATABASE_URL` (Postgres in compose, SQLite fallback locally) |
| ML | M5 model zoo, M6 condition router + explainers, M3 sklearn model |
| Federated learning | M3 (Flower 1.11.1, deterministic FedAvg; simulation + networked server/client) |
| Auth | M1 `auth.py` (user JWT), `service_auth.py` (scoped service tokens) |
| Admin | M7 (rounds, flags, overview, hospital oversight proxy to M1) |
| Synthesis | M8 (review packet; hard-coded `requires_clinician_review`) |
| Tests | per-module `test_*.py` + root `tests/` (incl. `tests/integration/test_e2e_flow.py`) |
| Docker | `docker-compose.yml`, one Dockerfile per module, `deploy/compose.env.example` |
| CI | `.github/workflows/ci.yml` |
| Docs | `README.md`, per-module `moduleN-*.md`, `docs/` |

Ports: M1 8001 · M2 8002 · M7 8005 · M8 8006 · Flower 8080 · dashboard 5173 (dev) / 80 in container.

---

## 2. Module map

| # | Directory | Purpose | Key files | Overall |
|---|---|---|---|---|
| 1 | `module1-auth` | Multi-tenant auth, hospital CRUD, vitals upload/review/export, audit | `main.py` (983 lines), `auth.py`, `service_auth.py`, `models.py`, `limits.py`, `audit.py`, `config.py`, `migrations/` | IMPLEMENTED |
| 2 | `module2-validation` | 5-stage validation gate (de-id, schema, ranges, cross-field, outliers) | `main.py`, `rules.py`, `schema.py`, `anomaly.py`, `service_auth.py` | IMPLEMENTED |
| 3 | `module3-fedlearning` | Local training + FedAvg (simulation and Flower server/client) | `server.py`, `client_runner.py`, `simulate*.py`, `fedavg.py`, `model.py`, `real_data.py`, `uci_heart.py` | PARTIAL |
| 4 | `module4-dashboard-react` | Login, upload, flagged review, federation map, admin views, synthesis view | `src/App.jsx`, `src/api.js`, `src/components/*` | IMPLEMENTED (no tests) |
| 5 | `module5-modelzoo` | Specialist-model interface, registry, router, fusion | `base.py`, `registry.py`, `router.py`, `fusion.py`, `models/*` | PARTIAL (most specialists are stubs here) |
| 6 | `module6-condition-router` | Condition → specialists + explainers; SHAP/Grad-CAM/KG | `conditions.py`, `condition_router.py`, `condition_registry_builder.py`, `explainers/`, `models/` | PARTIAL |
| 7 | `module7-admin` | Platform oversight: rounds, flags, overview, trigger | `main.py`, `models.py`, `hospitals_client.py`, `seed_demo.py` | IMPLEMENTED (no migrations) |
| 8 | `module8-synthesis` | Review-packet synthesis for clinicians | `main.py`, `synthesis.py`, `feature_mapper.py`, `model_provider.py` | PARTIAL (demo model only) |

---

## 3. Feature status

| Feature | Module | Status | Evidence / gap |
|---|---|---|---|
| Hospital creation / activation (super_admin only) | M1 | IMPLEMENTED | `POST/PATCH /hospitals`; unauthenticated call → 401 (observed) |
| Self-registration (forced `clinician`) | M1 | IMPLEMENTED | Role never read from payload. Public by design — see debt (open to any caller who knows a hospital id) |
| Admin user creation | M1 | IMPLEMENTED | `POST /admin/users`, super_admin only |
| Login / logout / cookie + Bearer | M1 | IMPLEMENTED | `/token`, `/logout`, `/me` |
| Hospital scoping from JWT, not client input | M1 | IMPLEMENTED | `vitals` queries filter on `current_user.hospital_id`; cross-hospital review blocked + audited (`main.py` ~L794) |
| Vitals upload JSON / CSV → M2 validation → store | M1+M2 | IMPLEMENTED | Covered by `test_uploads.py` and the e2e test |
| Flagged-record review (approve/reject) | M1 | IMPLEMENTED | `ReviewDecision` is `Literal["approve","reject"]` |
| Scoped service token for `/vitals/export` | M1 | IMPLEMENTED | Per-hospital `hid` claim; 401 without credential (observed) |
| Label provenance (`label_source`, `requires_label`) | M1 | IMPLEMENTED | Migration 0002 |
| Audit logging (structured JSON) | M1,M2,M7,M8 | IMPLEMENTED | `audit.py` ×4 identical copies |
| Request size / field limits | M1,M2 | IMPLEMENTED | `limits.py` |
| Fail-fast secrets/config | all services | IMPLEMENTED | `config.py`; unset `FEDHEAL_ENV` = production |
| CORS allow-list | M1,M7,M8 | IMPLEMENTED | From `FEDHEAL_DASHBOARD_ORIGIN`; `*` rejected |
| M2 requires service credential | M2 | IMPLEMENTED | 401 unauthenticated (observed) |
| De-identification screen / schema / ranges / cross-field / outliers | M2 | IMPLEMENTED | 38 tests. Range thresholds are rule definitions, not clinically validated |
| Local-only training baseline + FedAvg | M3 | IMPLEMENTED | `fedavg.py`, `simulate.py` |
| Flower networked server + hospital client runner | M3 | PARTIAL | Code + credential tests pass; **UNVERIFIED** end-to-end networked run. Plaintext gRPC, no TLS (documented) |
| Raw data never sent to aggregation | M3 | IMPLEMENTED (by design) | Client trains locally from M1 export with its own hospital-scoped token; only weights go to the server. Not independently audited at network level |
| Export of a federated global model for inference | M3→M8 | MISSING | M8 itself says it uses a demo fallback "until Module 3 exports a federated global model" |
| Round reporting to M7 | M3→M7 | IMPLEMENTED | Static per-hop key (`FEDHEAL_SVC_KEY_M3_M7`) |
| Overview / rounds / flags | M7 | IMPLEMENTED | 21 tests, all endpoints super_admin or service-key gated |
| Trigger training round | M7 | PARTIAL | `POST /admin/rounds/trigger` spawns `simulate.py` as a subprocess (prototype); not a real federated trigger, and not usable in a container image that doesn't contain M3 |
| DB migrations | M1 | IMPLEMENTED | Alembic 0001, 0002 (ran clean on SQLite) |
| DB migrations | M7 | MISSING | `Base.metadata.create_all()` at import (`main.py:54`) |
| Specialist interface, registry, router, fusion | M5 | IMPLEMENTED | `SpecialistModel`, `registry_status()` reports `is_stub`, `training_status`, `available` |
| Vitals specialist (XGBoost / TabPFN) | M5 | PARTIAL | Registry reports `xgboost-vitals-v1`, `untrained`, `available: False` until fitted. TabPFN not installed in this audit environment |
| Imaging, segmentation, foundation specialists (chest X-ray, retina, skin, CT, RadFM, BiomedParse, SegVol, OmiCLIP, Evo 2) | M5 | STUB | In this environment all 9 report `is_stub: True`, `training_status: none`. Real paths need torch/GPU/weights, none exercised. Stubs are labelled, which is correct |
| Condition registry (breast cancer, leukemia, DR, pneumonia, TB, skin cancer, heart disease) | M6 | IMPLEMENTED | Data table; only `heart_disease` has a runnable (non-stub) path here |
| SHAP explainer | M6 | IMPLEMENTED | Exercised by M6 and M8 tests |
| Grad-CAM, histopathology MIL, pathology foundation | M6 | STUB | Need torch; fall back to labelled stub |
| Knowledge-graph reasoner | M6 | PARTIAL | 106 lines present; not exercised beyond M6 tests. **UNVERIFIED** clinical content/provenance |
| Leukemia CBC / genomic expression models | M6 | PARTIAL | Code present; training data provenance **UNVERIFIED** |
| Explicit feature mapper (no imputation) | M8 | IMPLEMENTED | `feature_mapper.py`; missing field reported, never defaulted |
| `POST /synthesize/record` | M8 | IMPLEMENTED | Requires login, reads record with caller's own token, passed-validation only |
| Demo model gated outside development | M8 | IMPLEMENTED | 503 `specialist_unavailable` unless `FEDHEAL_ALLOW_DEMO_MODEL=true` |
| Legacy `/synthesize/heart_disease` | M8 | IMPLEMENTED (removed) | Returns 410 |
| Clinician-review guard | M8 | IMPLEMENTED | `requires_clinician_review` hard-coded in the packet; no diagnosis/treatment/dosage output |
| Dashboard: login, upload, flagged review | M4 | IMPLEMENTED | Builds; no automated UI tests |
| Dashboard: federation map, rounds rail, system map, admin actions | M4 | IMPLEMENTED | Admin views gated on `role === "super_admin"` client-side (server enforces the real check) |
| Dashboard: SynthesisView record picker | M4 | IMPLEMENTED | Picks a stored record id; no manual feature entry |
| Docker Compose full stack | root | PARTIAL | YAML only. File itself says "DRAFT… not yet built/run". **Docker is not available in this audit environment — UNVERIFIED** |
| CI | root | PARTIAL | Runs M1, M2, M5, M6, M7, M8, root tests, dashboard build. **Module 3 tests are not in CI** |

---

## 4. Roles, scoping, auth map

- Roles (M1 `Role` enum): `clinician`, `hospital_admin`, `super_admin`.
- User credential: JWT (HS256, `FEDMED_JWT_SECRET`), httpOnly cookie or Bearer. Claims: `sub`, `hospital_id`, `role`. M7 and M8 only verify.
- Service credentials (`X-Service-Key`): signed scoped tokens (claims `iss sub aud hid exp jti`), one signing key per hop:
  - M3→M1 `/vitals/export` (`FEDHEAL_SVC_SIGNING_KEY_M3_M1`, hospital-scoped, `aud=module1:vitals-export`)
  - M1→M2 `/validate/*` (`FEDHEAL_SVC_SIGNING_KEY_M1_M2`, minted per upload)
  - Directory listing (`aud=module1:hospital-directory`, only token allowed `hid="*"`)
  - M2→M7 and M3→M7 ingest: static per-hop keys (`FEDHEAL_SVC_KEY_M2_M7`, `FEDHEAL_SVC_KEY_M3_M7`), constant-time compare. **Not hospital-scoped** (see debt)
- Failure semantics: missing/forged/expired → 401; wrong role/audience/hospital → 403.
- Hospital scoping: derived from the JWT; client-supplied hospital ids are not trusted for user endpoints. `super_admin` is the only cross-hospital role.

---

## 5. API map

**Module 1 — auth / vitals (:8001)**

| Method | Path | Access |
|---|---|---|
| GET | `/health` | public |
| POST | `/register` | public (role forced to clinician) |
| POST | `/token`, `/logout` | credentials / cookie |
| GET | `/me` | any user |
| POST | `/hospitals` | super_admin |
| GET | `/hospitals` | any user, or scoped service token |
| PATCH | `/hospitals/{id}` | super_admin |
| POST | `/admin/users` | super_admin |
| POST | `/vitals/upload`, `/vitals/upload/csv` | user with hospital; forwards to M2 |
| GET | `/vitals`, `/vitals/{id}` | own hospital (super_admin any) |
| GET | `/vitals/flagged` | own hospital |
| POST | `/vitals/{id}/review` | own hospital; approve/reject |
| GET | `/vitals/export` | hospital-scoped service token only |
| GET | `/training-status` | authenticated |

**Module 2 — validation (:8002, internal):** `POST /validate/vitals`, `POST /validate/vitals/csv` (service token), `GET /health`.

**Module 7 — admin (:8005):** `GET /health`; `GET /admin/hospitals`, `PATCH /admin/hospitals/{id}`, `POST /admin/rounds/trigger`, `GET /admin/overview` (super_admin); `GET /admin/rounds`, `GET /admin/flags` (super_admin); `POST /admin/rounds`, `POST /admin/flags` (service key, M3 / M2).

**Module 8 — synthesis (:8006):** `GET /health`; `GET /models/status`, `POST /synthesize/record` (any logged-in user); `POST /synthesize/heart_disease` → 410.

**Module 3:** no HTTP API. Flower gRPC server on :8080 (`server.py`), clients via `client_runner.py`, simulations via `simulate.py` / `simulate_real.py`.

---

## 6. Database map

| Table | Module | Notes |
|---|---|---|
| `hospitals` | M1 | `id` (uuid str), `name` unique, `is_active`, `requires_label` |
| `users` | M1 | `email` unique, `hashed_password`, `role`, `hospital_id` FK (nullable for super_admin) |
| `vitals_records` | M1 | `hospital_id` FK indexed, `patient_ref`, age/height/weight, BP, HR, medication fields, `label`, `label_source`, `validation_status` (`passed`/`flagged`), `uploaded_at` |
| `training_rounds` | M7 | round number, n_hospitals, global_accuracy, baseline_accuracy, notes |
| `validation_flags` | M7 | `hospital_id` (plain string, **no FK**), status, reason, count |

Schema management: M1 Alembic (2 revisions). M7: `create_all`. The committed `module1-auth/fedmed_auth.db` is an empty SQLite file (0 rows in all 3 tables); it is gitignored via `*.db`, so it should not be in the archive.

---

## 7. Duplicated / unnecessary code

Intentional copies, enforced by `tests/test_shared_files_in_sync.py` (verified byte-identical by md5):

| File | Copies |
|---|---|
| `config.py` | 5 (M1, M2, M3, M7, M8) |
| `docs_theme.py` | 4 |
| `audit.py` | 4 (M1, M2, M7, M8) |
| `service_auth.py` | 3 (M1, M2, M3) |
| `limits.py` | 2 (M1, M2) |

Not removed: they work and are guarded by a test. Candidate for a shared package later, but that is a larger change than this audit warrants.

Other:
- `module8-synthesis/synthesis.py`, `main.py`, `demo.py` and M6 use `sys.path.insert` to reach sibling modules; Dockerfile and CI install sibling requirements to match.
- Three overlapping planning docs: `docs/DEVELOPMENT_PLAN.md`, `docs/16-week-development-plan.md`, `docs/SPRINT-*`.
- `module1-auth/__pycache__`, `module5-modelzoo/__pycache__` and the empty `.db` shipped in the archive.

---

## 8. Known technical debt

1. **Four docs are referenced but do not exist**: `docs/model-algorithm-catalog.md`, `docs/foundation-models-status.md`, `docs/development-plan-to-oct20.md`, `docs/module8-code-review-notes.md` (cited by README, M5/M6 docs and code comments). The README's "what's real vs. blocked" claims for foundation models point at a missing file.
2. **M7 has no migrations** (`create_all`), and shares a DB with M1 without FKs (`validation_flags.hospital_id` unconstrained).
3. **CI skips Module 3**; no dashboard tests; no Postgres run in CI.
4. **Docker Compose never built/run** (self-declared draft); no `/health`-based `depends_on` between app services.
5. **Dependency conflict**: `pip check` reports `shap 0.52.0` requires `numpy>=2` but M6/M8 pin `numpy` 1.26.4 (M8/M6 declare `numpy>=1.26`; M2/M3/M5 pin 1.26.4). Tests pass today; this is a latent install hazard.
6. **M7 → M3 trigger** shells out to `simulate.py` by relative path; will not work in the M7 container.
7. **Static (unscoped) keys for M2→M7 and M3→M7** ingest: a leaked key can post flags/rounds for any hospital.
8. **Open self-registration**: anyone knowing a hospital id can create a clinician for that hospital. No invite/approval step.
9. **No federated global model reaches inference**: M8 relies on a labelled demo model trained on public UCI data. No metrics from it should be presented as hospital or federated performance.
10. **Flower channel is plaintext gRPC** (documented; LAN only).
11. Deprecation noise: `datetime.utcnow()` (python-jose), pydantic v2 class-based `Config` (M7).

---

## 9. Test status (this audit, Python 3.12.3, `FEDHEAL_ENV=development`)

| Suite | Result |
|---|---|
| `module1-auth` | **149 passed** (78 s) |
| `module2-validation` | **38 passed** |
| `module3-fedlearning` | **15 passed** (not in CI) |
| `module5-modelzoo` | **6 passed** |
| `module6-condition-router` | **13 passed** |
| `module7-admin` | **21 passed** |
| `module8-synthesis` | **27 passed** |
| root `tests/` (integration + sync) | **14 passed** |
| **Total** | **283 passed, 0 failed** |
| `module4-dashboard-react` | `npm ci && npm run build` succeeded (27 modules); no tests exist |

Not run / not verifiable here: Docker build and compose, Postgres, real Flower networked rounds, torch/GPU/foundation specialists, TabPFN (skipped: disk).

---

## 10. Run commands (verified)

Per-module tests (from the module directory): `FEDHEAL_ENV=development python -m pytest -q`
Root/integration: `FEDHEAL_ENV=development python -m pytest -q tests`

Local start (I ran these; all four `/health` returned 200 and the protected endpoints returned 401 unauthenticated):

```
python -m venv .venv && . .venv/bin/activate
pip install -r module1-auth/requirements.txt -r module2-validation/requirements.txt \
            -r module7-admin/requirements.txt -r module8-synthesis/requirements.txt \
            -r module6-condition-router/requirements.txt -r module3-fedlearning/requirements.txt
export FEDHEAL_ENV=development FEDHEAL_DATABASE_URL=sqlite:////tmp/fedheal.db \
       FEDMED_JWT_SECRET=<dev-only-secret> FEDHEAL_DASHBOARD_ORIGIN=http://localhost:5173 \
       FEDMED_AUTH_API_URL=http://localhost:8001 FEDHEAL_AUTH_API_URL=http://localhost:8001 \
       FEDHEAL_VALIDATION_API_URL=http://localhost:8002 FEDHEAL_ADMIN_API_URL=http://localhost:8005
(cd module1-auth && alembic upgrade head)
(cd module1-auth && uvicorn main:app --port 8001)
(cd module2-validation && uvicorn main:app --port 8002)
(cd module7-admin && uvicorn main:app --port 8005)
(cd module8-synthesis && uvicorn main:app --port 8006)
(cd module4-dashboard-react && npm ci && npm run dev)     # :5173
```

Full stack (**UNVERIFIED here**): `cp deploy/compose.env.example .env`, replace every `CHANGE_ME`, `docker compose up --build`; add `--profile federation` for the Flower server.

Environment variables (see each `.env.example`): `FEDHEAL_ENV`, `FEDHEAL_DATABASE_URL` (`FEDHEAL_ADMIN_DATABASE_URL` for M7 override), `FEDMED_JWT_SECRET`, `FEDHEAL_DASHBOARD_ORIGIN`, `FEDHEAL_SVC_SIGNING_KEY_M3_M1`, `FEDHEAL_SVC_SIGNING_KEY_M1_M2`, `FEDHEAL_SVC_KEY_M2_M7`, `FEDHEAL_SVC_KEY_M3_M7`, `FEDHEAL_SVC_TOKEN_M3_M1`, `FEDHEAL_AUTH_API_URL`, `FEDMED_AUTH_API_URL`, `FEDHEAL_VALIDATION_API_URL`, `FEDHEAL_ADMIN_API_URL`, `FEDHEAL_ALLOW_DEMO_MODEL`, optional `FEDHEAL_MAX_*` limits; dashboard `VITE_AUTH_API_BASE`, `VITE_ADMIN_API_BASE`, `VITE_SYNTHESIS_API_BASE`. Staging/production require ≥32-char non-placeholder secrets and https origins.

---

## 11. Recommended implementation order

The security pass (P0) and the M1→M8 integration pass are already present in this code. Remaining, smallest-risk first:

1. **Restore the four missing docs** (or remove the references) so claims about foundation models and plans are not dangling. Docs only.
2. **Baseline hygiene**: drop `__pycache__` and the empty `.db` from the archive; add Module 3 to CI; resolve the `shap`/`numpy` pin conflict and re-run all suites.
3. **Verify Docker/Compose** on a machine with Docker, with Postgres; fix whatever surfaces. Add `/health` healthchecks and `depends_on: service_healthy`.
4. **M7 migrations** (Alembic) and decide whether `validation_flags.hospital_id` becomes a real FK.
5. **Scope M2→M7 / M3→M7 ingest** to a hospital claim (reuse `service_auth.py`, no new auth system).
6. **Self-registration control** (invite code or admin approval) — behavior change, needs a decision.
7. **Replace M7's subprocess trigger** with a defined M3 entry point that works in containers.
8. **Federated model export M3 → M8** with a documented provenance record, so the demo-model fallback can be retired. Only then report any model metrics, and only the ones the run actually produces.
9. **Dashboard tests** (login, scoping, flagged review, synthesis error states).
10. Imaging/foundation specialists last; each needs real weights, hardware, and validation data that this repository does not contain.


---

## 12. Update after P0 implementation (2026-10-06)

| Feature | Status | Existing Location | Required Change |
|---|---|---|---|
| Authentication | IMPLEMENTED | M1 `auth.py`, `main.py` | Disabled-account check added; open registration remains (decision needed) |
| Hospital management | IMPLEMENTED | M1 `/hospitals` | None |
| Doctor management | IMPLEMENTED (new) | M1 `cases.py` `/hospital/doctors` | Password reset / invite flow |
| Patient Case | IMPLEMENTED (new) | M1 `models.Case`, `cases.py` | Delete/archive policy |
| Medical history | IMPLEMENTED (new) | M1 `models.MedicalHistory` | Not a model input yet |
| Vitals | IMPLEMENTED | M1 + M2; now linked via `case_id` | Temperature / SpO2 / resp. rate not in M2 schema |
| Scan upload | MISSING | — | P1 |
| AI inference | PARTIAL | M8 `/cases/{id}/analyze`, M5/M6 | Serve a registry-promoted model |
| Explainability | IMPLEMENTED for vitals (SHAP) | M6/M8 | Image explainers are stubs |
| Federated learning | PARTIAL | M3 + `federation_registry.py` | TLS, clipping, DP, secure aggregation absent |
| Model registry | IMPLEMENTED (new) | M7 `model_registry.py` | M7 still uses `create_all`; no Alembic |
| Clinician review | IMPLEMENTED (new) | M1 `/cases/{id}/review` | Not stored against a specific analysis |
| Security | PARTIAL | see SECURITY.md | See known gaps there |
| Testing | PARTIAL | see TESTING.md | No browser E2E; no clean-install/Docker run |

# Module reference

This inventory is based on the current source tree. HTTP details are
consolidated in [API_REFERENCE.md](API_REFERENCE.md).

## Configuration name guide

| Name | Purpose |
|---|---|
| `FEDHEAL_ENV` | Selects development/test versus staging/production validation behavior. |
| `FEDHEAL_DB_BACKEND` | Selects Firestore, local JSON, or memory persistence where supported. |
| `FEDMED_JWT_SECRET` | Signs/verifies human user JWTs. |
| `FEDHEAL_SVC_SIGNING_KEY_*` | Signs/verifies a specific service-to-service token hop. |
| `FEDHEAL_*_API_URL` / `FEDMED_AUTH_API_URL` | Service base URLs used for internal HTTP calls. |
| `FEDHEAL_DASHBOARD_ORIGIN` | Explicit browser CORS allow-list. |
| `FEDHEAL_ALLOW_DEMO_MODEL` | Explicitly enables the non-clinical UCI fallback in Module 8. |
| `VITE_*_API_BASE` | Build-time browser API base URLs for the dashboard. |

## Module 1 — `module1-auth`

**Responsibility:** user authentication, tenant identity, hospitals, doctors,
cases, structured history, vitals, scans, analyses, reviews, audit events, and
the Module 1 storage boundary.

**Entry point and key files:** `main.py` (FastAPI app and auth/vitals routes);
`cases.py` (case router); `auth.py` (password/JWT); `service_auth.py`
(internal tokens); `models.py` (entities and collection names); `repo.py` and
`docstore.py` (persistence); `database.py` (backend selection);
`create_super_admin.py` and `mint_service_token.py` (operations).

**Public API:** `GET /health`; `POST /hospitals`, `GET /hospitals`,
`PATCH /hospitals/{hospital_id}`; `POST /register`, `POST /admin/users`,
`POST /token`, `POST /logout`, `GET /me`; `POST /vitals/upload`,
`POST /vitals/upload/csv`, `GET /vitals`, `GET /vitals/{record_id}`,
`GET /vitals/flagged`, `POST /vitals/{record_id}/review`,
`GET /vitals/export`, `GET /training-status`; `POST/GET /hospital/doctors`,
`PATCH /hospital/doctors/{doctor_id}`; `POST/GET /cases`,
`GET/PATCH /cases/{case_id}`, `PUT/GET /cases/{case_id}/history`,
`POST/GET /cases/{case_id}/vitals`, `POST/GET /cases/{case_id}/scans`,
`POST/GET /cases/{case_id}/analyses`, and `POST/GET
/cases/{case_id}/review(s)`. Auth and response summaries are in
[API_REFERENCE.md](API_REFERENCE.md).

**Configuration:** `FEDHEAL_ENV`, `FEDHEAL_DB_BACKEND`,
`FEDHEAL_FIREBASE_PROJECT_ID`, `FEDHEAL_FIRESTORE_DATABASE`,
`GOOGLE_APPLICATION_CREDENTIALS`, `FIRESTORE_EMULATOR_HOST`,
`FEDMED_JWT_SECRET`, `FEDHEAL_SVC_SIGNING_KEY_M3_M1`,
`FEDHEAL_SVC_SIGNING_KEY_M1_M2`, `FEDHEAL_VALIDATION_API_URL`,
`FEDHEAL_DASHBOARD_ORIGIN`, `FEDHEAL_COOKIE_SECURE`,
`FEDHEAL_ALLOW_PUBLIC_REGISTRATION`, `FEDHEAL_LOCAL_STORE_PATH`, upload-limit
variables, and upload/scanning settings read by `config.py`/`limits.py`.

**Dependencies:** calls Module 2 for validation; serves Module 3 exports;
serves Module 4 and Module 8 caller-scoped reads/writes. Status: **implemented,
with local/Firestore backend alternatives**.

## Module 2 — `module2-validation`

**Responsibility:** stateless vitals validation and count-only flag reporting.

**Entry point and key files:** `main.py`, `schema.py`, `rules.py`,
`anomaly.py`, `limits.py`, `service_auth.py`, `audit.py`.

**Public API:** `POST /validate/vitals` and `POST /validate/vitals/csv`
(Module 1 service token) return per-record validation verdicts; `GET /health`
is public liveness. Request/response details are in
[API_REFERENCE.md](API_REFERENCE.md).

**Configuration:** `FEDHEAL_ENV`, `FEDHEAL_SVC_SIGNING_KEY_M1_M2`,
`FEDHEAL_SVC_SIGNING_KEY_M2_M7`, `FEDHEAL_ADMIN_API_URL`,
`FEDHEAL_DASHBOARD_ORIGIN`, and the shared upload-limit variables.

**Dependencies:** called by Module 1; optionally reports summaries to Module
7. Status: **implemented pipeline; no persistent database**.

## Module 3 — `module3-fedlearning`

**Responsibility:** hospital-local training, Flower network transport,
deterministic FedAvg, dataset preparation, and candidate/round reporting.

**Entry point and key files:** `server.py`, `client_runner.py`, `client.py`,
`model.py`, `fedavg.py`, `real_data.py`, `data.py`, `federation_registry.py`,
`privacy.py`, `seed_uci_heart.py`, `compare_uci_heart.py`,
`simulate.py`, and `simulate_real.py`.

**Public API:** no owned HTTP API. The Flower server listens on the configured
address (Compose maps 8080). It calls Module 1 `GET /hospitals` and
`GET /vitals/export`, and Module 7 round/retraining/candidate endpoints.

**Configuration:** `.env.example` lists `FEDHEAL_ENV` and
`FEDHEAL_AUTH_API_URL`; code also reads `FEDHEAL_ADMIN_API_URL`,
`FEDHEAL_SVC_TOKEN_M3_M1`, `FEDHEAL_SVC_TOKEN_M3_M7`,
`FEDHEAL_MODEL_STORAGE_PATH`, `FEDHEAL_VITALS_FEATURE_SCHEMA`,
`FEDHEAL_UPDATE_CLIP_NORM`, `FEDHEAL_UPDATE_NOISE_MULTIPLIER`, and runner
arguments/environment used for service access.

**Dependencies:** Modules 1 and 7; Flower, NumPy, scikit-learn. Status:
**implemented synthetic and networked paths; cross-machine/TLS deployment not
verified**. `simulate_real.py` intentionally refuses centralized raw-data
pooling.

## Module 4 — `module4-dashboard-react`

**Responsibility:** browser UI for login, hospital/federation views, uploads,
flag reviews, cases, synthesis, rounds, and system visualization.

**Entry point and key files:** `src/main.jsx`, `src/App.jsx`, `src/api.js`,
`src/components/`, `src/styles/`, `package.json`, and `vite.config.js`.

**Public API:** no server API; browser client calls Module 1, Module 7, and
Module 8 endpoints listed in [API_REFERENCE.md](API_REFERENCE.md).

**Configuration:** `VITE_AUTH_API_BASE`, `VITE_ADMIN_API_BASE`,
`VITE_SYNTHESIS_API_BASE`. Status: **implemented UI; browser E2E not verified**.

## Module 5 — `module5-modelzoo`

**Responsibility:** specialist-model contracts, registry, fusion, runnable
tabular vitals model, and explicit imaging/foundation stubs/fallbacks.

**Entry point and key files:** `base.py`, `registry.py`, `router.py`,
`fusion.py`, `models/tabular_vitals.py`, `models/stub.py`, and model files
under `models/`.

**Public API:** no HTTP endpoints. Status: **library implemented; many
specialists are dependency/model-data gated or stubs**. It is imported by
Modules 6 and 8.

## Module 6 — `module6-condition-router`

**Responsibility:** condition alias resolution, specialist selection, and
explanation attachment.

**Entry point and key files:** `conditions.py`, `condition_router.py`,
`condition_registry_builder.py`, `paths.py`, `explainers/`, and `models/`.

**Public API:** no HTTP endpoints. Status: **routing contracts implemented;
Grad-CAM, knowledge graph, and many specialist paths are partial/stubbed**.
Imported by Module 8 and uses Module 5.

## Module 7 — `module7-admin`

**Responsibility:** platform overview, training rounds, count-only validation
flags, retraining queue, model registry, validation gate, promotion, and
rollback.

**Entry point and key files:** `main.py`, `model_registry.py`,
`hospitals_client.py`, `models.py`, `schemas.py`, `repo.py`, `docstore.py`,
`database.py`, and `mint_retraining_runner_token.py`.

**Public API:** `GET /health`; `GET /admin/hospitals`,
`PATCH /admin/hospitals/{hospital_id}`, `POST/GET /admin/rounds`,
`POST /admin/rounds/trigger`, `POST /admin/retraining/eligibility`,
`GET /admin/retraining/requests/next`,
`POST /admin/retraining/requests/complete`,
`GET /admin/retraining/requests/{request_id}/candidate`,
`GET /admin/retraining/requests`, `POST/GET /admin/flags`,
`GET /admin/overview`, `POST/GET /admin/models/candidates`,
`GET /admin/models`, `POST /admin/models/{model_id}/validate`,
`POST /admin/models/{model_id}/promote`, `POST /admin/models/rollback`,
`GET /admin/models/promoted`, and `GET /admin/models/current`. Auth and
response summaries are in [API_REFERENCE.md](API_REFERENCE.md).

**Configuration:** `FEDHEAL_ENV`, database/Firebase variables,
`FEDHEAL_ADMIN_FIRESTORE_DATABASE`, `FEDMED_JWT_SECRET`,
`FEDHEAL_SVC_SIGNING_KEY_M2_M7`, `FEDHEAL_SVC_SIGNING_KEY_M3_M7`,
`FEDHEAL_SVC_SIGNING_KEY_M8_M7`, `FEDMED_AUTH_API_URL`,
`FEDHEAL_RETRAIN_MIN_ELIGIBLE_RECORDS`, and dashboard origin. Status:
**implemented; no scheduler and no automatic promotion**.

## Module 8 — `module8-synthesis`

**Responsibility:** caller-scoped record/case analysis, promoted-model lookup,
condition routing, explanations, structured synthesis, considerations, and
explicit imaging-unavailable responses.

**Entry point and key files:** `main.py`, `synthesis.py`, `model_provider.py`,
`promoted_model.py`, `feature_mapper.py`, `considerations.py`,
`imaging_analysis.py`, `auth.py`, and `service_auth.py`.

**Public API:** `GET /health`, `GET /models/status`, `POST /synthesize/record`,
`POST /cases/{case_id}/analyze`,
`POST /cases/{case_id}/scans/{scan_id}/analyze`, and retired
`POST /synthesize/heart_disease` (410). Auth and response summaries are in
[API_REFERENCE.md](API_REFERENCE.md).

**Configuration:** `FEDHEAL_ENV`, `FEDHEAL_AUTH_API_URL`,
`FEDMED_JWT_SECRET`, `FEDHEAL_DASHBOARD_ORIGIN`,
`FEDHEAL_SVC_SIGNING_KEY_M8_M7`, `FEDHEAL_ADMIN_API_URL`, and
`FEDHEAL_ALLOW_DEMO_MODEL`. Status: **implemented HTTP path; imaging and
non-vitals inputs are partial/unavailable**.

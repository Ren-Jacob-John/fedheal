# FedHeal — Implementation Report

## Client-server restructure (2026-10-22)

The repository was restructured on branch
`ren-jacob-john-restructure-client-server` without changing business logic,
API contracts, authentication behavior, or security rules.

### What moved

- `module4-dashboard-react` -> `client/dashboard`
- Modules 1, 2, 5, 6, 7, and 8 -> `server/auth`, `server/validation`,
  `server/model-zoo`, `server/condition-router`, `server/admin`, and
  `server/synthesis`
- Module 3 central aggregation -> `server/federated-server`
- Module 3 hospital-local client, data loading, simulations, and demo dataset
  -> `hospital-node`
- Compose, Firebase, Firestore, and deployment examples -> `infra`
- Added `scripts/run-all`, `scripts/run-one`, and `scripts/test-all` for both
  PowerShell and Linux/macOS

All moves used `git mv` and were committed by logical group. The complete
mapping, risks, path audit, and open questions are in
[`docs/RESTRUCTURE_PLAN.md`](docs/RESTRUCTURE_PLAN.md).

The byte-identical shared files (`service_auth.py`, `audit.py`,
`docs_theme.py`, and `limits.py`) were verified by SHA-256 but remain
service-local. Their current flat-import and container working-directory
semantics make consolidation risky for a structural-only refactor; the
decision is documented in `server/shared/README.md`.

### Verification before vs. after

| Check | Before | After |
|---|---|---|
| Backend pytest invocations | 7 invocations, all exit 5 (`no tests ran`) | 8 invocations after the module 3 split, all exit 5 (`no tests ran`) |
| Dashboard production build | Passed; 28 modules | Passed; 28 modules |
| Python compile check | Not part of the baseline | Passed for `server` and `hospital-node` |
| Moved-service import smoke check | Not run | Passed for auth, validation, admin, synthesis, federated-server, and condition-router in development mode |
| Docker Compose config | Not verified at baseline | Passed with `infra/deploy/compose.env.example` |
| Local health checks | Not run | Auth, validation, admin, synthesis, and dashboard returned HTTP 200 |
| Federated server boot | Not run | Process started and remained running until deliberately stopped |

The initial health pass had a transient startup race for validation and
synthesis; a retry after the processes reached readiness returned HTTP 200
for both. The complete Docker image build/Compose runtime was not run.

### Remaining open questions

- Historical test files described by older documentation are absent from this
  checkout, so no backend pass count beyond “no tests ran” can be claimed.
- The shared-file consolidation remains intentionally deferred; see
  `server/shared/README.md`.
- `firebase-debug.log` remains tracked under `infra/` because removing it was
  outside the requested structural scope.
- Full multi-process federated training with real hospital data and Docker
  health orchestration still requires its external services, credentials, and
  eligible data.

---

The earlier implementation status below is retained as historical context.
Items are labelled IMPLEMENTED / PARTIAL / NOT IMPLEMENTED.

## IMPLEMENTED
- **Onboarding:** super_admin → hospital → hospital_admin → doctors (create / list / disable, own hospital only; foreign `hospital_id` → 403, audited). **Public self-registration is closed by default** (`FEDHEAL_ALLOW_PUBLIC_REGISTRATION`). Disabled accounts cannot log in and their tokens stop working.
- **Clinical data:** cases (Alembic 0003, indexed), structured medical history, vitals linked to cases (validated by Module 2, rejects never stored), clinician review (`ACCEPTED|OVERRIDDEN|NEEDS_MORE_DATA`; never a training label), scan upload (0004).
- **Tenancy:** derived from the authenticated user; other hospital's case → 403 + audit on every sub-resource. Hospital admins and super_admin have no patient-level access. Verified A→B and B→A, also through the real M1+M2+M8 services.
- **Analysis (`POST /cases/{id}/analyze`, Module 8):** condition only from case metadata (`CONDITION_NOT_SET` otherwise); only available modalities used; `INSUFFICIENT_DATA` with the named missing inputs; `MODEL_UNAVAILABLE` when no model/registry; unsupported-scan conditions → explicit unavailable; model status/provenance/federated flag in every report; safety banner; `clinician_review_required: true`; no treatment/dosage/diagnosis text.
- **Promoted federated model → inference:** Module 8 reads the promoted model from the registry, re-hashes the weights, and serves it (≤5 s cache). The demo fallback exists only behind `FEDHEAL_ALLOW_DEMO_MODEL=true`, is labelled NON-CLINICAL DEMO, and is never used silently when the registry is down. Proven end to end with the demo flag OFF; the prediction is reproduced from the registry's weights.
- **Federation:** real two-hospital run (public UCI data seeded through Modules 1/2), local training on each hospital's own validated records, FedAvg, pooled-holdout evaluation, aggregate-only candidate. Raw data never leaves Module 1; client outputs and the registry are tested to hold only weights/aggregates; the registry refuses patient-like fields and re-derives the weight hash.
- **Registry (Module 7, Alembic 0001):** candidate → gate (integrity, participation, data quality, minimum metrics, beats-majority-baseline, regression vs deployed, cross-site gap) → explicit super_admin promotion → rollback; a failed/regressing candidate preserves the production model.
- **Service-to-service auth:** static shared keys replaced by short-lived signed tokens with a key per hop (caller, audience, hospital scope, expiry). Module 2→7 flags are hospital-scoped (mismatch → 403).
- **Migrations / deployment:** Alembic for Modules 1 and 7 (zero model drift; coexist in one DB via separate version tables; Dockerfile runs `alembic upgrade head`); M7 `create_all` only in local tiers. Compose gained health checks and startup ordering (`depends_on: service_healthy`).
- **Dashboard:** Cases / Doctors tabs: create case, vitals, history, scan upload, run analysis, report (modalities, model status, provenance, explanation, warnings), clinician review; loading/error/empty/unauthorized states. `npm run build` succeeds.
- **CI** runs Module 3 tests; integration job installs Modules 3 and 7.

## PARTIAL
- **Scans:** stored and linked with strict validation; **no analysis exists** (no validated imaging model). Files are unencrypted on local disk.
- **Federated privacy:** raw-data isolation implemented; **TLS, update clipping, differential privacy, secure aggregation are NOT implemented** (stated in every candidate's metadata and in docs/FEDERATED_PRIVACY.md). FedAvg is not formal privacy protection.
- **Model quality:** the recorded real run (2 hospitals, public UCI, 3 informative features) scored 0.591 on n=44 (majority floor 0.545) and was **rejected by the default gate**. It is promoted only under an explicitly relaxed test policy, to prove the wiring. Gate metrics are self-reported by the training side. Nothing here generalises to hospital patients.
- **Tests:** no browser E2E (Playwright). The "dashboard completes the workflow" criterion is covered by the same API calls in `tests/integration/test_doctor_workflow.py` plus a successful build — not a browser run.

## NOT IMPLEMENTED
Image/lab analysis; temperature/SpO2/respiratory-rate vitals (would change model dimension and M2 schema); persisted AI-analysis records (reviews are not bound to a specific analysis); password reset/invite; TLS; Docker/Compose run, Postgres run, clean-machine install; demo recording and screenshots; rate limiting beyond `/token`.

## Tests (Python 3.12, SQLite, `FEDHEAL_ENV=development`)
**408 passed, 0 failed, 0 skipped** — M1 199 · M2 38 · M3 20 · M5 6 · M6 13 · M7 53 · M8 51 · root/integration 28 (baseline before this work: 283). `npm run build` OK. Docker/Compose: **unverified** (YAML parses; health-check/ordering logic not exercised).
Intentional changes to existing tests: CORS now allows PUT (history upsert); several M1 tests set `FEDHEAL_ALLOW_PUBLIC_REGISTRATION=true` because they exercise the open path's escalation guards; M8 tests set the explicit demo flag; M7/config tests use the new signing-key names; the e2e helper onboards via admin → doctor instead of `/register`.

## Modified (important)
M1: `models.py`, `main.py`, `cases.py` (new), migrations 0003/0004 · M2: `main.py` · M3: `simulate*.py`, `federation_registry.py` (new), `seed_uci_heart.py` · M4: `CasesView.jsx` (new), `api.js`, `App.jsx`, `TopHUD.jsx`, `app.css` · M7: `models.py`, `auth.py`, `main.py`, `model_registry.py` (new), `migrations/` (new), Dockerfile · M8: `main.py`, `promoted_model.py` (new), `model_provider.py` · shared `service_auth.py` (×5), `audit.py` (×4) · `infra/docker-compose.yml`, `infra/deploy/compose.env.example`, `.env.example` files, CI, docs.

## Known limitations / risks
Demo and gate thresholds are engineering defaults, not clinical criteria. `DEPLOYED` means "passed this platform's gate and was promoted", never "clinically validated". The `/cases/*` JSON endpoints rely on field validation rather than the body-size middleware. The Flower channel is plaintext. The aggregation server sees each hospital's individual update.

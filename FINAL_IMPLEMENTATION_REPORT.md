# FedHeal — Implementation Report (INTERIM, 2026-10-06)

This is an honest interim report, not a "done" declaration. The Definition of Done is **not** fully met
(see Known Limitations).

## Completed
- Audit → `docs/IMPLEMENTATION_STATUS.md` (+ §12 post-P0 table).
- Hospital isolation extended to all new entities; tested A→B and B→A on every case sub-resource.
- Hospital admin → doctor create / list / disable (own hospital only; foreign `hospital_id` → 403, audited);
  disabled accounts cannot log in and existing tokens stop working.
- Patient Case / Encounter (Alembic 0003, indexed), structured Medical History (upsert, bounded), vitals
  linked to cases (validated by Module 2, rejects not stored), Clinician Review
  (`ACCEPTED|OVERRIDDEN|NEEDS_MORE_DATA`, never used as training labels).
- `POST /cases/{id}/analyze` (Module 8): modalities available/missing, model status
  (`UNAVAILABLE|STUB|FALLBACK`), uncertainty, SHAP explanation, `INSUFFICIENT_DATA` / `MODEL_UNAVAILABLE`,
  safety banner, `clinician_review_required: true`; no treatment/dosage content.
- Model registry in Module 7: candidate → validation gate (integrity, participation, data quality, minimum
  metrics, beats-majority baseline, regression vs deployed, cross-site gap) → explicit super_admin
  promotion → rollback; registry refuses raw-data-shaped payloads.
- Module 3 exports the federated global model (sha256 of weights) and registers an aggregate-only candidate.
- Doctor dashboard workflow (Cases / Doctors tabs) with loading, error, empty and unauthorized states.
- CI now runs Module 3 tests; integration job installs Modules 3 and 7.
- Docs: MODEL_STATUS, FEDERATED_PRIVACY, MVP_SCOPE, TESTING, API, ARCHITECTURE, DEMO_RUNBOOK, SECURITY additions.

## Modified files (important)
`module1-auth/{models.py,main.py,migrations/versions/0003_*.py,test_security.py}` ·
`module7-admin/{models.py,main.py}` · `module8-synthesis/main.py` ·
`module3-fedlearning/simulate_real.py` · `module{1,2,7,8}/audit.py` (allow-list: case_id, resource_type,
resource_id, model_version) · `module4-dashboard-react/src/{App.jsx,api.js,components/TopHUD.jsx,styles/app.css}` ·
`.github/workflows/ci.yml` · `.gitignore` · `README.md` · `docs/IMPLEMENTATION_STATUS.md`, `docs/SECURITY.md`.

## New files
`module1-auth/{cases.py,test_cases.py}` · `module7-admin/{model_registry.py,test_model_registry.py}` ·
`module8-synthesis/test_case_analysis.py` · `module3-fedlearning/{federation_registry.py,test_federation_registry.py}` ·
`module4-dashboard-react/src/components/CasesView.jsx` ·
`tests/integration/{test_doctor_workflow.py,test_federation_flow.py}` · the new docs listed above.

## Tests (this environment, Python 3.12, `FEDHEAL_ENV=development`)
Total: **372**  Passed: **372**  Failed: **0**  Skipped: **0**
(M1 186 · M2 38 · M3 20 · M5 6 · M6 13 · M7 45 · M8 39 · root/integration 25). Baseline before this work: 283.
Dashboard `npm run build` succeeds. Not run: Docker, Postgres, browser E2E.
Two existing M1 CORS assertions were changed on purpose (PUT is now an allowed method for history upsert).

## AI models
| Name | Version | Status | Dataset | Metrics | Limitations |
|---|---|---|---|---|---|
| xgboost-vitals-v1 (served) | uci-cleveland-demo-1 | FALLBACK | public UCI Cleveland | none claimed | 3 real features of 8; uncalibrated; not hospital-trained or federated |
| vitals-fedavg-logreg (candidate) | v1 | REJECTED by gate in recorded run | public UCI via 2 seeded hospitals | acc 0.591, n=44, majority floor 0.545 | tiny holdout; not served for inference |
| All imaging / foundation specialists | — | STUB / UNAVAILABLE | none | none | need torch, weights, validation data |

## Federated learning
Two hospitals (seeded from public data through Module 1/2), local training on each hospital's own validated
records, weighted FedAvg, pooled-holdout evaluation, candidate registration, validation gate, human promotion.
Raw data never leaves Module 1; the registry and client outputs are tested to hold aggregates/weights only.

## Security
Authentication: JWT + disabled-account checks. Authorization: RBAC + hospital tenancy on all new endpoints.
Upload security: only existing vitals limits (no scan upload exists). Audit logging: ids only, tested.
TLS: **not implemented**. Differential privacy: **not implemented**. Update clipping: **not implemented**.
Secure aggregation: **not implemented**.

## Known limitations (be skeptical of anything not listed as done)
1. No scan/image upload or image inference. No lab data. Temperature/SpO2/respiratory rate are not supported (Module 2 schema).
2. No federated or registry model is served for inference; analysis uses the FALLBACK demo model.
3. Medical history is shown as context; **it is not a model input**.
4. AI analyses are computed on request and not persisted; reviews are not tied to a specific analysis.
5. The only recorded federated candidate was REJECTED by the gate; promotion/rollback are proven with synthetic metrics in unit tests, not with a passing real model.
6. Gate thresholds are engineering defaults; metrics are self-reported by Module 3.
7. Module 7 has no Alembic migrations. Open self-registration remains. New case endpoints lack request-size middleware and rate limits.
8. Docker Compose, Postgres, and a clean-machine install were not run. No browser E2E (Playwright). No demo recording or screenshots.
9. Flower traffic is plaintext; the federation server sees individual updates.

## Future work
Scan upload (+DICOM/PACS), image models with validated weights, more diseases, stronger privacy (TLS, clipping,
DP, secure aggregation), serving promoted models, persisted analyses, browser E2E, production deployment,
larger datasets, regulatory/compliance work.

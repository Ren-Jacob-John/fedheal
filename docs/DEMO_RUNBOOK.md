# Demo runbook (synthetic / public data only)

**Execution status:** this remains a runbook, not a claim of a completed
Compose demo. The current environment had no Docker executable and only
Python 3.14.6 (CI targets Python 3.12). Compose YAML parsing and focused
service tests were run, but Compose, Firestore emulator, and browser
workflow were not executed here. The Playwright spec exists and a CI job is
configured, but neither has been executed in this environment. The Compose stack uses the Firestore
emulator, not Postgres, matching the repository's current Firestore data
layer.

```
python -m venv .venv && . .venv/bin/activate
pip install -r module1-auth/requirements.txt -r module2-validation/requirements.txt \
  -r module3-fedlearning/requirements.txt -r module6-condition-router/requirements.txt \
  -r module7-admin/requirements.txt -r module8-synthesis/requirements.txt
export FEDHEAL_ENV=development \
  FEDHEAL_DASHBOARD_ORIGIN=http://localhost:5173 FEDHEAL_BOOTSTRAP_ADMIN_PASSWORD=demo-bootstrap-password-1
(cd module1-auth && python create_super_admin.py --email admin@demo.local)
(cd module1-auth && uvicorn main:app --port 8001) &   (cd module2-validation && uvicorn main:app --port 8002) &
(cd module7-admin && uvicorn main:app --port 8005) &  (cd module8-synthesis && uvicorn main:app --port 8006) &
(cd module4-dashboard-react && npm ci && npm run dev) &
```

Services also need (development defaults exist for the signing keys; set real ones outside local use):
`FEDHEAL_ADMIN_API_URL=http://localhost:8005` for Modules 3 and 8. To see the promoted model answer,
**do not** set `FEDHEAL_ALLOW_DEMO_MODEL` (leave the demo fallback off). Public registration stays closed.

1. **Hospitals + admins.** Log in as `admin@demo.local`; create "Hospital A" and "Hospital B"
   (`POST /hospitals`), then a hospital_admin for each (`POST /admin/users`, role `hospital_admin`).
2. **Doctor.** Log in as Hospital A's admin → dashboard tab *Doctors* → create a doctor.
3. **Case.** Log in as that doctor → tab *Cases* → create `PAT-DEMO-001`, condition Heart disease.
4. **Vitals, history, scan.** Enter vitals (leave unknown fields blank — nothing is filled in), a history, and
   optionally a PNG/JPEG scan (stored and linked; the report will say analysis is unavailable).
5. **Before any model is promoted:** *Run AI analysis* → `MODEL_UNAVAILABLE` (the demo fallback is off). This is correct.
6. **Federated lifecycle verification (optional).** From the repository root,
   run `python -m pytest -q tests/integration/test_federation_flow.py`. This
   integration test starts throwaway real services, seeds public UCI records,
   adds clearly marked synthetic records to cross a one-record test threshold,
   and has hospital-scoped runners perform a networked Flower round. A
   provenance-complete aggregate is registered as CANDIDATE; the test then
   exercises the validation gate, explicit super-admin promotion, and
   inference. Its relaxed test gate is for wiring verification only, not a
   model-quality claim. Do not run `simulate_real.py`: central pooling of
   hospital records is disabled by the privacy boundary.
7. **Gate and promotion.** The integration test exercises these as separate
   super-admin actions after candidate registration; the default gate is not
   relaxed by normal runtime configuration, and retraining never promotes a
   candidate automatically.
8. **Analysis.** In the manual Compose walkthrough, keep the demo fallback
   disabled unless deliberately enabling the labelled NON-CLINICAL public-data
   model. A promoted federated model is served only after the validation gate
   and explicit promotion; its response includes its version/status and
   provenance.
9. **Review.** Submit Accepted / Overridden / Needs more data with a note;
   review decisions are not used as training labels.
10. **Isolation.** As Hospital B's doctor, request Hospital A's case id → 403 (see the audit log).
11. **Rollback.** After a second promoted version exists, `POST /admin/models/rollback?model_name=vitals-fedavg-logreg&condition=heart_disease`.

The integration test uses throwaway local document stores; it is not a
Compose/Firestore-emulator run. Docker Compose (`docker-compose.yml`, with
health checks and startup ordering) has **not** been run here.
The queue-triggered two-hospital integration test was executed locally and
passed: 7 passed. It runs services and Flower clients as separate processes;
it does not establish that the workflow works across Docker containers.

## Browser E2E (synthetic, explicitly labelled demo analysis)

The Playwright workflow in Module 4 requires the stack to be running and a
super_admin to be provisioned. Set `FEDHEAL_E2E_SUPER_ADMIN_EMAIL` and
`FEDHEAL_E2E_SUPER_ADMIN_PASSWORD`; `FEDHEAL_E2E_AUTH_API_URL` is optional
and defaults to `http://localhost:8001`. To let the synthetic workflow reach
analysis without a promoted model, configure the local stack with
`FEDHEAL_ALLOW_DEMO_MODEL=true`. This deliberately enables only the labelled
NON-CLINICAL demo model; do not use it for clinical or production data.

From `module4-dashboard-react`, install dependencies and Chromium and run the
test with `npm ci`, `npx playwright install chromium`, then
`npm run test:e2e`. The repository CI `browser-e2e` job provisions
development-only secrets and the Compose/Firestore emulator services before
running this same browser flow. The CI workflow has been configured but not
executed as part of this runbook verification.

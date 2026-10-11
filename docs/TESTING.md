# Testing

```
export FEDHEAL_ENV=development
for m in module1-auth module2-validation module3-fedlearning module5-modelzoo \
         module6-condition-router module7-admin module8-synthesis; do (cd $m && python -m pytest -q); done
python -m pytest -q tests            # real services: e2e, doctor workflow, two-hospital federation -> promotion -> inference
cd module4-dashboard-react && npm ci && npm run build
npm run test:e2e                     # Playwright browser flow (requires stack and Chromium)
```

## Current verification (2026-10-11)

Only Python 3.14.6 is installed in the current environment; CI pins Python
3.12. The pristine root `pytest -q` baseline had 1 skipped test and 6
collection errors. The current focused runs were:

| Command / area | Result |
|---|---|
| `module1-auth`: `python -m pytest -q test_analyses.py` | 7 passed |
| `module2-validation`: `test_security.py` | 46 passed (earlier focused run) |
| `module3-fedlearning`: `python -m pytest -q` | 39 passed |
| `module5-modelzoo`: focused suite | 6 passed (earlier run) |
| `module6-condition-router`: focused suite | 11 passed, 2 failed due to the known SHAP/Python 3.14 runtime incompatibility |
| `module7-admin`: `python -m pytest -q` | 63 passed; malformed `NaN` test sends raw JSON so the API itself verifies refusal |
| `module8-synthesis`: `test_imaging_analysis.py test_scan_analysis_endpoint.py` | 7 passed |
| `module8-synthesis`: imaging + scan endpoint + case-analysis focused selectors | 25 passed |
| `module8-synthesis`: full suite | 66 passed, 1 failed; pre-existing SHAP-unavailable expectation |
| Real-service doctor workflow: `tests/integration/test_doctor_workflow.py` | 7 passed |
| Queue-triggered two-hospital Flower lifecycle: `tests/integration/test_federation_flow.py` | 7 passed; separate service processes, throwaway local stores, candidate → gate → explicit promotion → inference |
| Flower real-network comparison: `test_client_runner_matches_simulation.py --hospitals 2 --records-per-hospital 20 --rounds 2` | Comparison printed PASS within tolerance; process then exited nonzero because Windows cleanup found `module1.log` still open |
| Dashboard: `npm run build` | Passed; Vite transformed 28 modules |
| Playwright: `npm run test:e2e -- --list` | Discovered 1 spec; browser flow not run |
| CI browser E2E | `browser-e2e` job configured to provision development Compose/emulator services and run Chromium; job not executed here |

The previous record of a zero-failure Python 3.12 run is not reproduced in
this environment. The broad Module 1 suite was interrupted after more than
six minutes of CPU-bound work. There are no dashboard unit tests. Docker/
Compose, the Firestore emulator, and Playwright browser execution were not
run. The Flower comparison did execute both networked clients, but its
temporary log handle prevented clean process exit on Windows; a successful
exit for that script is not claimed.
The initial dashboard baseline also reported one high-severity npm audit
advisory from the unchanged dependency lockfile; no dependency changes were
made as part of this work.

| Acceptance item | Where |
|---|---|
| Doctor creation / disable, no cross-hospital creation | `module1-auth/test_cases.py::TestDoctors`, `tests/integration/test_doctor_workflow.py` |
| Public registration closed by default | `test_cases.py::TestRegistrationClosed` |
| Case / history / scan / analysis tenancy, A↔B both directions | `test_cases.py`, `test_doctor_workflow.py::test_hospital_isolation_*` (real M1+M2+M8) |
| Incomplete data → explicit missing inputs | `module8-synthesis/test_case_analysis.py`, `test_promoted_model.py`, `test_doctor_workflow.py` |
| Scan upload validation and status-only scan analysis, including tenancy | `test_cases.py::TestScans`, `test_case_analysis.py`, `test_scan_analysis_endpoint.py` |
| Registry: candidate → validate → promote → rollback; hash re-derivation; raw-data refusal | `module7-admin/test_model_registry.py` |
| Scoped service tokens (hospital scope, audience, expiry) | `module7-admin/test_security.py::TestServiceKeys` |
| Retraining queue threshold, one active claim, hospital scope, failed/completed baseline behavior | `module7-admin/test_security.py` |
| Real two-hospital FedAvg; federation output has no raw fields | `test_federation_flow.py`, `module3-fedlearning/test_federation_registry.py`, `test_client_runner_matches_simulation.py` |
| Inference loads the PROMOTED model, not a demo model | `module8-synthesis/test_promoted_model.py`, `test_federation_flow.py::test_inference_serves_exactly_the_promoted_model_with_provenance` (demo flag OFF; prediction reproduced from registry weights) |
| Before promotion nothing is served | `test_federation_flow.py::test_before_promotion_*` |
| Data layer | `module1-auth/test_docstore.py`: one contract suite for every backend (memory, JSON file, and the Firestore emulator when `FIRESTORE_EMULATOR_HOST` is set), repository uniqueness, entity mapping, backend selection |
| Move off Supabase | `migrate_from_sql.py` (M1, M7) exercised end to end from a SQLite database built with the OLD models: ids, roles, labels, flagged/passed counts, JSON lists and model weights verified after the copy |

Firestore: the tests run on the local store, which implements the same interface. The Firestore backend itself is
checked offline (queries and batches are built by the real `google-cloud-firestore` library and inspected), but it has
**not** been run against real Firestore or the emulator in this repository's CI. Do that before relying on it:

```
firebase emulators:start --only firestore          # firebase.json at the repo root
FIRESTORE_EMULATOR_HOST=localhost:8080 python -m pytest -q module1-auth/test_docstore.py
```

Not covered: browser E2E runtime, TLS, load/performance, queue-triggered candidate registration across separate containers, real Firestore (indexes, quotas, latency), Docker/Compose.

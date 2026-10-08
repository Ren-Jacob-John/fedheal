# Testing

```
export FEDHEAL_ENV=development
for m in module1-auth module2-validation module3-fedlearning module5-modelzoo \
         module6-condition-router module7-admin module8-synthesis; do (cd $m && python -m pytest -q); done
python -m pytest -q tests            # real services: e2e, doctor workflow, two-hospital federation -> promotion -> inference
cd module4-dashboard-react && npm ci && npm run build     # no UI tests exist
```

Last full run (Python 3.12, SQLite): **408 passed, 0 failed** — M1 199 · M2 38 · M3 20 · M5 6 · M6 13 · M7 53 · M8 51 · root 28.

| Acceptance item | Where |
|---|---|
| Doctor creation / disable, no cross-hospital creation | `module1-auth/test_cases.py::TestDoctors`, `tests/integration/test_doctor_workflow.py` |
| Public registration closed by default | `test_cases.py::TestRegistrationClosed` |
| Case / history / scan / analysis tenancy, A↔B both directions | `test_cases.py`, `test_doctor_workflow.py::test_hospital_isolation_*` (real M1+M2+M8) |
| Incomplete data → explicit missing inputs | `module8-synthesis/test_case_analysis.py`, `test_promoted_model.py`, `test_doctor_workflow.py` |
| Scan upload validation; unsupported scan conditions → explicit unavailable | `test_cases.py::TestScans`, `test_case_analysis.py` |
| Registry: candidate → validate → promote → rollback; hash re-derivation; raw-data refusal | `module7-admin/test_model_registry.py` |
| Scoped service tokens (hospital scope, audience, expiry) | `module7-admin/test_security.py::TestServiceKeys` |
| Real two-hospital FedAvg; federation output has no raw fields | `test_federation_flow.py`, `module3-fedlearning/test_federation_registry.py` |
| Inference loads the PROMOTED model, not a demo model | `module8-synthesis/test_promoted_model.py`, `test_federation_flow.py::test_inference_serves_exactly_the_promoted_model_with_provenance` (demo flag OFF; prediction reproduced from registry weights) |
| Before promotion nothing is served | `test_federation_flow.py::test_before_promotion_*` |
| Migrations | M1 and M7 Alembic: upgrade/downgrade and zero model drift verified (see below) |

Migration check: `alembic upgrade head` on a fresh SQLite for each module; `compare_metadata` reports 0
differences; both histories coexist in one database (separate version tables); downgrade works.

Not covered: browser E2E, TLS, load/performance, Postgres, Docker/Compose.

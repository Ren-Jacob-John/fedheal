# Testing

```
export FEDHEAL_ENV=development
for m in module1-auth module2-validation module3-fedlearning module5-modelzoo \
         module6-condition-router module7-admin module8-synthesis; do (cd $m && python -m pytest -q); done
python -m pytest -q tests            # real services: e2e, doctor workflow, two-hospital federation
cd module4-dashboard-react && npm ci && npm run build     # no UI tests exist
```

P0 coverage: `module1-auth/test_cases.py` (doctors, cases, history, case vitals, review, A↔B isolation
on every sub-resource, audit logs carry no clinical content); `module8-synthesis/test_case_analysis.py`
(modalities, FALLBACK status, INSUFFICIENT_DATA, MODEL_UNAVAILABLE, no treatment text);
`module7-admin/test_model_registry.py` (gate, promotion, rollback, regression, raw-data refusal);
`module3-fedlearning/test_federation_registry.py`; `tests/integration/test_doctor_workflow.py` and
`test_federation_flow.py`.

Not covered: browser E2E, scan upload, TLS, load/performance, Postgres.

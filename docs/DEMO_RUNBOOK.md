# Demo runbook (synthetic / public data only)

```
python -m venv .venv && . .venv/bin/activate
pip install -r module1-auth/requirements.txt -r module2-validation/requirements.txt \
  -r module3-fedlearning/requirements.txt -r module6-condition-router/requirements.txt \
  -r module7-admin/requirements.txt -r module8-synthesis/requirements.txt
export FEDHEAL_ENV=development FEDHEAL_DATABASE_URL=sqlite:////tmp/fedheal.db \
  FEDHEAL_DASHBOARD_ORIGIN=http://localhost:5173 FEDHEAL_BOOTSTRAP_ADMIN_PASSWORD=demo-bootstrap-password-1
(cd module1-auth && alembic upgrade head && python create_super_admin.py --email admin@demo.local)
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
6. **Federation.** `cd module3-fedlearning && FEDHEAL_SEED_SUPER_ADMIN_EMAIL=admin@demo.local FEDHEAL_SEED_SUPER_ADMIN_PASSWORD=$FEDHEAL_BOOTSTRAP_ADMIN_PASSWORD python seed_uci_heart.py --hospitals 2 && python simulate_real.py`
   → two hospitals train locally on their own validated records; a CANDIDATE is registered (aggregates + weights only). It is **not** deployed.
7. **Gate.** `POST /admin/models/{id}/validate` as super_admin. Under the **default policy** this public-data run is
   **rejected** (see MODEL_STATUS.md) and `promote` returns 409. That is the honest result.
8. **See promotion → inference.** Restart Module 7 with the *demo/test* policy used by the integration test
   (`FEDHEAL_GATE_MIN_ACCURACY=0.5 FEDHEAL_GATE_MIN_EVAL_EXAMPLES=30 FEDHEAL_GATE_MAX_HOSPITAL_GAP=0.6 FEDHEAL_GATE_MIN_MARGIN_OVER_MAJORITY=0.0`),
   re-run `simulate_real.py`, validate (passes), `POST /admin/models/{id}/promote`. These relaxed thresholds exist only to demonstrate
   the wiring; they are not a claim that the model is good.
9. **Analysis with the promoted model.** As the doctor, *Run AI analysis*: the report shows the promoted version, `federated`,
   weights hash, round, 2 hospitals, "not clinically validated", the linear-contribution explanation, missing inputs and the safety banner.
10. **Review.** Submit Accepted / Overridden / Needs more data with a note.
11. **Isolation.** As Hospital B's doctor, request Hospital A's case id → 403 (see the audit log).
12. **Rollback.** After a second promoted version exists, `POST /admin/models/rollback?model_name=vitals-fedavg-logreg&condition=heart_disease`.

Steps 5–9 are exactly what `tests/integration/test_federation_flow.py` automates against the real services.
Docker Compose (`docker-compose.yml`, now with health checks and startup ordering) has **not** been run in this environment.

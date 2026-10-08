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

1. **Hospitals + admins.** Log in as `admin@demo.local`; create "Hospital A" and "Hospital B"
   (`POST /hospitals`), then a hospital_admin for each (`POST /admin/users`, role `hospital_admin`).
2. **Doctor.** Log in as Hospital A's admin → dashboard tab *Doctors* → create a doctor.
3. **Case.** Log in as that doctor → tab *Cases* → create `PAT-DEMO-001`, condition Heart disease.
4. **Vitals + history.** Enter vitals (leave unknown fields blank — nothing is filled in) and a history; save.
5. **AI analysis.** *Run AI analysis*. Expect: model status **FALLBACK**, scan/labs listed as missing,
   banner "AI Clinical Decision Support — Not a Diagnosis". Remove diastolic BP and re-run to see `INSUFFICIENT_DATA`.
6. **Review.** Submit Accepted / Overridden / Needs more data with a note.
7. **Isolation.** As Hospital B's doctor, request Hospital A's case id → 403 (also visible in the audit log).
8. **Federation.** `cd module3-fedlearning && FEDHEAL_SEED_SUPER_ADMIN_EMAIL=admin@demo.local FEDHEAL_SEED_SUPER_ADMIN_PASSWORD=$FEDHEAL_BOOTSTRAP_ADMIN_PASSWORD python seed_uci_heart.py --hospitals 2 && python simulate_real.py`
   → a CANDIDATE is registered; it is **not** deployed.
9. **Gate.** `POST /admin/models/{id}/validate` as super_admin. With the recorded public-data run the
   gate **rejects** the candidate (see MODEL_STATUS.md); `promote` then returns 409 and nothing changes.
   Promotion and rollback mechanics are demonstrated by `module7-admin/test_model_registry.py` (synthetic metrics).

Docker Compose (`docker-compose.yml`) is a draft that has not been run in this environment.

# Architecture

See the diagram and module map in IMPLEMENTATION_STATUS.md. P0 additions:

```
Hospital → Users (hospital_admin creates doctors)
         → Cases ─┬ Vitals (case_id, validated by Module 2)
                  ├ MedicalHistory (1 per case)
                  ├ ClinicianReviews
                  └ AI analysis (Module 8, computed on request, not stored)
Module 3 (per-hospital training) → FedAvg → candidate (aggregates + weight hash only)
   → Module 7 registry: CANDIDATE → validate → VALIDATED|REJECTED → promote (super_admin) → DEPLOYED → rollback
```

Tenancy: Module 1 owns hospital-scoped data; every query filters on the authenticated user's
hospital. Module 8 reads case data **as the calling user**, so Module 1's checks apply to it too.
Admins (hospital_admin, super_admin) have no patient-level access by design.

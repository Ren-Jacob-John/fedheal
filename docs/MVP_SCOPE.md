# MVP scope (target: 2026-10-10)

Implemented: platform → hospital → hospital_admin → doctor onboarding (public registration closed);
hospital-isolated cases, structured medical history, case-linked validated vitals, scan upload
(store + link only); clinician review; `POST /cases/{id}/analyze` over the **promoted federated model**
(demo fallback only behind an explicit flag, labelled NON-CLINICAL); two-hospital FedAvg through the real
services; model registry with weight-hash verification, validation gate, explicit promotion and rollback;
scoped service-to-service tokens; Alembic for Modules 1 and 7; doctor dashboard workflow.

Explicitly **not** done: image/lab analysis (no validated imaging model — scans are stored only);
extra vitals (temperature, SpO2, respiratory rate); TLS, update clipping, differential privacy, secure
aggregation; persisted AI-analysis records; browser-level (Playwright) E2E; a Docker/Compose run;
Postgres run; demo recording and screenshots.

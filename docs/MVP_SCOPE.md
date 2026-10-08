# MVP scope (target: 2026-10-10)

In scope and implemented: hospital isolation; hospital_admin → doctor creation/disable; patient
cases; structured medical history; vitals linked to cases; one runnable model (labelled FALLBACK);
`POST /cases/{id}/analyze`; clinician review; two-hospital FedAvg run; model registry, validation gate,
promotion and rollback; doctor dashboard workflow; security/isolation tests; docs.

Explicitly **not** done (see FINAL_IMPLEMENTATION_REPORT.md): scan/image upload and image inference;
lab data; additional vital signs (temperature, SpO2, respiratory rate — Module 2's schema has no such
fields); TLS, clipping, DP, secure aggregation; serving a registry model for inference; persisted
AI-analysis records; browser-level (Playwright) E2E; a clean-machine Docker run; demo recording and
screenshots; rate limiting beyond `/token`.

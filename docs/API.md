# API additions (P0)

Auth: `Authorization: Bearer <JWT>` or the session cookie. Hospital is always derived from the session.

**Module 1 (:8001)** — clinical data is `clinician` only; other hospital's case → 403 (audited).
`POST/GET /hospital/doctors`, `PATCH /hospital/doctors/{id}` (hospital_admin; body `hospital_id` must be absent or own) ·
`POST/GET /cases`, `GET/PATCH /cases/{id}` · `PUT/GET /cases/{id}/history` ·
`POST/GET /cases/{id}/vitals` (one validated record) · `POST/GET /cases/{id}/scans` (multipart `scan_type` + `file`; PNG/JPEG ≤ 5 MB; stored and linked, **analysis UNAVAILABLE**; 422/413 `INVALID_FILE`) · `POST /cases/{id}/review`
(`ACCEPTED|OVERRIDDEN|NEEDS_MORE_DATA`, `clinician_note`, optional same-case `analysis_id`), `GET /cases/{id}/reviews` ·
`POST/GET /cases/{id}/analyses` (append-only; hospital-scoped; structured output/ids only).

**Module 8 (:8006)** — `POST /cases/{id}/analyze`: 200 with modalities, findings, confidence + uncertainty,
evidence, explanation, `model{name,version,status}`, warnings, `stub_or_fallback`,
`reasoning`, `suggested_considerations`, and `clinician_review_required: true`.
Errors: 422 `INSUFFICIENT_DATA`, 422/503 `MODEL_UNAVAILABLE`, 403, 404.
`POST /cases/{case_id}/scans/{scan_id}/analyze` checks scan membership through
Module 1 using the caller's JWT, then returns `status: analysis_unavailable`,
`message: "analysis unavailable: no validated imaging model"`,
`model_status: UNAVAILABLE`, null finding/confidence/heatmap/model version,
and `requires_clinician_review: true`. It does not retrieve or transmit image
bytes and does not claim an imaging result. Cross-hospital and unlinked scans
are refused.

**Module 7 (:8005)** — `POST /admin/models/candidates` (Module 3 service key) · `GET /admin/models` ·
`POST /admin/models/{id}/validate` · `POST /admin/models/{id}/promote` ·
`POST /admin/models/rollback?model_name=&condition=` · `GET /admin/models/current` (super_admin) · `GET /admin/models/promoted?condition=` (Module 8 service token; weights + provenance of the DEPLOYED model, 404 if none).
Candidate registration carries `parameters` (weights) and `input_spec`; the registry re-derives `artifact_hash` from them. Service credentials: signed tokens in `X-Service-Key` (see SECURITY.md).
Networked Flower final-round registration additionally requires complete
hospital/request provenance and eligible-count attestations; otherwise no
candidate is registered and queue completion is withheld. Registered models
remain CANDIDATE until validation and explicit super_admin promotion.
The runner can poll `GET /admin/retraining/requests/next`, check its linked
candidate at `GET /admin/retraining/requests/{request_id}/candidate`, and
complete through `POST /admin/retraining/requests/complete`, all scoped to
its hospital token.

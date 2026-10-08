# API additions (P0)

Auth: `Authorization: Bearer <JWT>` or the session cookie. Hospital is always derived from the session.

**Module 1 (:8001)** — clinical data is `clinician` only; other hospital's case → 403 (audited).
`POST/GET /hospital/doctors`, `PATCH /hospital/doctors/{id}` (hospital_admin; body `hospital_id` must be absent or own) ·
`POST/GET /cases`, `GET/PATCH /cases/{id}` · `PUT/GET /cases/{id}/history` ·
`POST/GET /cases/{id}/vitals` (one validated record) · `POST /cases/{id}/review`
(`ACCEPTED|OVERRIDDEN|NEEDS_MORE_DATA`, `clinician_note`), `GET /cases/{id}/reviews`.

**Module 8 (:8006)** — `POST /cases/{id}/analyze`: 200 with modalities, findings, confidence + uncertainty,
evidence, explanation, `model{name,version,status}`, warnings, `stub_or_fallback`,
`clinician_review_required: true`. Errors: 422 `INSUFFICIENT_DATA`, 422/503 `MODEL_UNAVAILABLE`, 403, 404.

**Module 7 (:8005)** — `POST /admin/models/candidates` (Module 3 service key) · `GET /admin/models` ·
`POST /admin/models/{id}/validate` · `POST /admin/models/{id}/promote` ·
`POST /admin/models/rollback?model_name=&condition=` · `GET /admin/models/current` (super_admin).

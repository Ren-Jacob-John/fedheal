# API reference

Examples use placeholders such as `<USER_JWT>` and `<SERVICE_JWT>`. They are
not real credentials. JSON response details are represented by the source
model names and status fields; use each service's `/docs` endpoint for the
generated schema.

## Module 1 — port 8001

| Method and path | Auth/role | Request and response summary |
|---|---|---|
| `GET /health` | None | Liveness: status object. |
| `POST /token` | Email/password form | Returns `access_token`; sets `fedheal_token` cookie. |
| `POST /logout` | User session | Clears the session cookie. |
| `GET /me` | User JWT/cookie | Returns current user and role/hospital. |
| `POST /hospitals` | `super_admin` | Creates a hospital. |
| `GET /hospitals` | User JWT or scoped Module 3 token | Lists hospital directory data; service tokens are restricted by scope. |
| `PATCH /hospitals/{hospital_id}` | `super_admin` | Changes hospital status/label requirement. |
| `POST /register` | Public only if explicitly enabled | Creates a clinician; otherwise returns forbidden. |
| `POST /admin/users` | `super_admin` | Creates a hospital admin or super admin. |
| `POST /vitals/upload` | Authenticated hospital user | Validates/stores JSON records; returns passed/flagged/rejected summaries. |
| `POST /vitals/upload/csv` | Authenticated hospital user | Multipart CSV equivalent. |
| `GET /vitals`, `GET /vitals/{record_id}` | Authenticated, hospital-scoped | Lists/gets stored records. |
| `GET /vitals/flagged` | Hospital admin/super admin, scoped | Lists flagged records. |
| `POST /vitals/{record_id}/review` | Hospital admin/super admin, scoped | Approves or rejects a flagged record. |
| `GET /vitals/export` | Hospital-scoped Module 3 token | Exports eligible records; `labeled_only` defaults to true. |
| `GET /training-status` | Authenticated | Returns counts/readiness for the caller's hospital or platform view. |
| `POST/GET /hospital/doctors` | Hospital admin/super admin | Creates/lists doctors. |
| `PATCH /hospital/doctors/{doctor_id}` | Hospital admin/super admin | Activates/deactivates a doctor. |
| `POST/GET /cases` | Clinician, hospital-scoped | Creates/lists cases. |
| `GET/PATCH /cases/{case_id}` | Clinician, hospital-scoped | Reads/updates a case. |
| `PUT/GET /cases/{case_id}/history` | Clinician, hospital-scoped | Upserts/reads structured history. |
| `POST/GET /cases/{case_id}/vitals` | Clinician, hospital-scoped | Adds/lists case-linked vitals. |
| `POST/GET /cases/{case_id}/scans` | Clinician, hospital-scoped | Uploads/lists scan metadata. |
| `POST/GET /cases/{case_id}/analyses` | Clinician, hospital-scoped | Appends/lists structured analysis history. |
| `POST/GET /cases/{case_id}/review(s)` | Clinician, hospital-scoped | Creates/lists clinician review decisions. |

Example:

```bash
curl -X GET http://localhost:8001/me -H "Authorization: Bearer <USER_JWT>"
curl -X POST http://localhost:8001/vitals/upload \
  -H "Authorization: Bearer <USER_JWT>" -H "Content-Type: application/json" \
  -d '{"records":[{"patient_ref":"demo-1","age_years":55,"height_cm":170,"weight_kg":75,"systolic_bp":130,"diastolic_bp":80,"heart_rate_bpm":72}]}'
```

## Module 2 — port 8002

| Method and path | Auth/role | Summary |
|---|---|---|
| `GET /health` | None | Liveness. |
| `POST /validate/vitals` | Module 1 `X-Service-Key: <SERVICE_JWT>` | Validates a JSON batch; returns per-record verdicts and reasons. |
| `POST /validate/vitals/csv` | Module 1 service JWT | Validates multipart CSV with the same pipeline. |

```bash
curl -X POST http://localhost:8002/validate/vitals \
  -H "X-Service-Key: <SERVICE_JWT>" -H "Content-Type: application/json" \
  -d '{"records":[],"require_label":false,"hospital_id":"<HOSPITAL_ID>"}'
```

## Module 7 — port 8005

| Method and path | Auth/role | Summary |
|---|---|---|
| `GET /health` | None | Liveness. |
| `GET /admin/hospitals` | `super_admin` JWT | Proxies Module 1 hospital data. |
| `PATCH /admin/hospitals/{hospital_id}` | `super_admin` JWT | Proxies hospital status update. |
| `POST /admin/rounds` | Module 3 service JWT | Records aggregate round metadata. |
| `GET /admin/rounds` | `super_admin` JWT | Lists rounds. |
| `POST /admin/rounds/trigger` | `super_admin` JWT | Returns/creates queue trigger behavior; does not launch a process. |
| `POST /admin/retraining/eligibility` | Scoped Module 3 runner JWT | Reports an eligible-record count. |
| `GET /admin/retraining/requests/next` | Scoped runner JWT | Claims/gets the next hospital request. |
| `POST /admin/retraining/requests/complete` | Scoped runner JWT | Completes a request after candidate linkage. |
| `GET /admin/retraining/requests/{request_id}/candidate` | Scoped runner JWT | Gets candidate/lifecycle status. |
| `GET /admin/retraining/requests` | `super_admin` JWT | Lists retraining requests. |
| `POST /admin/flags` | Module 2 service JWT | Records count-only validation flags. |
| `GET /admin/flags` | `super_admin` JWT | Lists flag summaries. |
| `GET /admin/overview` | `super_admin` JWT | Returns platform overview. |
| `POST/GET /admin/models/candidates` / `/admin/models` | Module 3 service JWT for POST; `super_admin` for GET | Registers/lists model versions. |
| `POST /admin/models/{model_id}/validate` | `super_admin` JWT | Applies validation gate. |
| `POST /admin/models/{model_id}/promote` | `super_admin` JWT | Promotes a validated model. |
| `POST /admin/models/rollback` | `super_admin` JWT | Rolls back to a prior deployment. |
| `GET /admin/models/promoted` | Module 8 promoted-model service JWT | Reads the currently promoted model for inference. |
| `GET /admin/models/current` | `super_admin` JWT | Reads the current registry model for operator use. |

```bash
curl http://localhost:8005/admin/overview \
  -H "Authorization: Bearer <SUPER_ADMIN_JWT>"
```

## Module 8 — port 8006

| Method and path | Auth/role | Summary |
|---|---|---|
| `GET /health` | None | Liveness. |
| `GET /models/status?condition=heart_disease` | Any authenticated user | Reports specialist source/status. |
| `POST /synthesize/record` | Any authenticated user, hospital-scoped record | Body contains `record_id` and `condition`; returns prediction, explanation/status, warnings, and synthesis. |
| `POST /cases/{case_id}/analyze` | Any authenticated hospital user | Builds and persists a structured case review packet. |
| `POST /cases/{case_id}/scans/{scan_id}/analyze` | Any authenticated hospital user | Returns explicit imaging unavailable status; does not transmit scan bytes. |
| `POST /synthesize/heart_disease` | Any caller | Retired endpoint; returns HTTP 410. |

```bash
curl -X POST http://localhost:8006/synthesize/record \
  -H "Authorization: Bearer <USER_JWT>" -H "Content-Type: application/json" \
  -d '{"record_id":"<RECORD_ID>","condition":"heart_disease"}'
```

## Module 3, 4, 5, and 6

Module 3 exposes Flower transport rather than a REST API. Modules 4, 5, and 6
do not expose HTTP servers in the current source tree. Module 4 is the client
of Modules 1, 7, and 8; Modules 5 and 6 are imported libraries.

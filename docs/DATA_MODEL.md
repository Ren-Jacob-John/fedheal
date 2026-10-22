# Data model

## Storage backends

Module 1 and Module 7 use `docstore.py` through `repo.py`. `FEDHEAL_DB_BACKEND`
selects Firestore, a development JSON-file store, or an in-memory backend.
Firestore documents are created on first write; there is no runtime schema
migration. `infra/firestore.rules` denies all direct client reads and writes.

## Module 1 collections

| Collection | Main fields and relationships |
|---|---|
| `hospitals` | `id`, `name`, `is_active`, `requires_label`. Tenant root. |
| `users` | `id`, `email`, `hashed_password`, `role`, optional `hospital_id`, `full_name`, `is_active`, `created_at`. |
| `vitals_records` | `hospital_id`, optional `case_id`, `patient_ref`, age/height/weight, optional blood pressure/heart rate/temperature/SpO2/respiratory rate, medication counts, optional `label`, `label_source`, `validation_status`, `has_label`, `uploaded_at`. |
| `cases` | `hospital_id`, `patient_ref`, `encounter_id`, `admission_reason`, optional `current_condition`, symptoms, status, creator/timestamps. |
| `medical_histories` | one structured document per case: conditions, diagnoses, surgeries, allergies, medications, family history, admissions, symptoms, notes, creator/timestamps. |
| `scans` | `case_id`, `hospital_id`, `scan_type`, server file reference, sniffed content type, size/hash, status, uploader/timestamp. |
| `ai_analyses` | `hospital_id`, `case_id`, model version/status, optional artifact hash, inputs used, missing inputs, structured output, creator/timestamp. |
| `clinician_reviews` | `case_id`, `hospital_id`, `doctor_id`, decision, optional `analysis_id` and note, timestamp. Reviews are not training labels. |
| `hospital_names`, `user_emails` | uniqueness/index documents maintained by the repository. |

Relationships are application-enforced string references. `hospital_id` scopes
all tenant data. `medical_histories` uses the case id as its document key for
one history per case.

## Module 7 collections

| Collection | Main fields |
|---|---|
| `training_rounds` | round number, hospital count, global/baseline accuracy, notes, report timestamp. |
| `retraining_requests` | hospital, eligible count, threshold bucket, baseline, lifecycle status, candidate id, claim/completion timestamps. |
| `retraining_progress` | hospital and count baseline fields. |
| `validation_flags` | hospital, `flagged`/`rejected` status, reason, count, report timestamp. |
| `model_versions` | model/version/condition, training round, participating hospitals, training metadata, metrics, validation status/report, deployment status, artifact hash, parameters/input spec, approval metadata. |

Module 7 proxies hospital identity/status to Module 1 rather than storing a
second hospital collection.

## Indexes

`infra/firestore.indexes.json` defines composite indexes for:

- cases by `hospital_id` and descending `created_at`;
- vitals by hospital/patient, hospital/validation status/patient,
  hospital/descending upload time, and case/hospital/descending upload time;
- reviews and scans by case/hospital/created time;
- analyses by case/hospital/descending created time;
- validation flags by hospital/descending report time;
- retraining requests by hospital/descending creation time;
- model versions by condition/descending creation time.

There are no field overrides in the checked-in index file.

## Security rules

`infra/firestore.rules` matches every document path and sets `allow read, write: if
false`. Clients therefore cannot access Firestore directly. Server-side
credentials bypass these client rules; tenant checks remain in the application
repositories/routes.

## Leftover SQL/Alembic code

`server/auth` and `server/admin` still contain `alembic.ini`, migration
templates, old SQLite artifacts, and `migrate_from_sql.py`. The active database
path is the Firestore/local docstore implementation; the migration scripts are
one-off import tooling, not the request-time persistence path. No Supabase
client is used by the active service code verified here.

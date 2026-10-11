# Moving FedHeal from Supabase (Postgres) to Firebase (Firestore)

Supabase was only ever a hosted Postgres here — the services used SQLAlchemy and Alembic, and nothing used
Supabase Auth/Storage. So the move is a data-layer change in **Module 1** (auth, cases, vitals) and
**Module 7** (rounds, flags, model registry). Auth is still FedHeal's own JWT system; Firebase Auth is not used.

## What changed

| Before | Now |
|---|---|
| SQLAlchemy models + queries in endpoints | dataclasses (`models.py`), explicit methods (`repo.py`), one storage interface (`docstore.py`, identical copy in M1 and M7) |
| `FEDHEAL_DATABASE_URL` / `FEDHEAL_ADMIN_DATABASE_URL` | `FEDHEAL_DB_BACKEND`, `FEDHEAL_FIREBASE_PROJECT_ID`, Google credentials |
| Alembic migrations on container start | none: collections appear on first write; indexes are `firestore.indexes.json` |
| SQLite fallback in development | local JSON-file store (`FEDHEAL_LOCAL_STORE_PATH`) |
| `postgres` service in Compose | Firestore **emulator** service in Compose (data is lost when it stops) |

Backend selection (`FEDHEAL_DB_BACKEND`): `firestore` (default in staging/production), `local` (default in
development), `memory` (tests). `local`/`memory` are refused outside development/test; the emulator
(`FIRESTORE_EMULATOR_HOST`) is refused in production.

## One-time Firebase setup

1. Create a Firebase project and enable **Firestore in Native mode** (pick the region carefully — it can't be changed).
2. Create a service account with the *Cloud Datastore User* role. Give the key to Modules 1 and 7 as
   `GOOGLE_APPLICATION_CREDENTIALS` (or run them with an attached service account on Cloud Run/GCE — preferred).
3. Set `FEDHEAL_FIREBASE_PROJECT_ID` for both services. Optionally give Module 7 its own database with
   `FEDHEAL_ADMIN_FIRESTORE_DATABASE`.
4. Deploy rules and indexes **before** the first request — ordered queries fail with `FAILED_PRECONDITION` until
   their composite indexes finish building:
   ```
   firebase deploy --only firestore:rules,firestore:indexes
   ```
   `firestore.rules` denies every direct client read/write; only the services (service account) touch the data.

## Copying the existing Supabase data

Run from each module folder, with the destination configured exactly as the service will be (steps 2–3 above).
The source is only read.

```
pip install sqlalchemy psycopg2-binary                     # needed by the script only
cd module1-auth
python migrate_from_sql.py --source-url "postgresql://postgres.<ref>:<password>@<host>:5432/postgres" --dry-run
python migrate_from_sql.py --source-url "postgresql://..."
cd ../module7-admin && python migrate_from_sql.py --source-url "postgresql://..."
```

- Ids are preserved, so issued JWTs, case links and Module 3's hospital-scoped service tokens keep working.
- Re-running is safe (every write is an upsert). Password hashes are copied as-is; nobody resets a password.
- **Scan files are not copied** — they live on disk under `FEDHEAL_UPLOAD_STORAGE_PATH`; Firestore only holds their metadata.
- Suggested order: stop writes → dry run → copy → compare counts → start the services on Firestore → smoke-test
  login, a case, an upload, `/training-status` → keep the Supabase project until you're satisfied.

## Behaviour differences you should know about

- **No unique constraints.** E-mail and hospital-name uniqueness is enforced with small index documents
  (`user_emails`, `hospital_names`) written atomically with the entity; a concurrent duplicate loses with a 400.
  One history per case is structural (document id = case id).
- **Bulk uploads are chunked** (≤450 writes per batch). A very large upload is no longer all-or-nothing if a
  later chunk fails. Single-record, review and promote/rollback writes are atomic.
- **Check-then-write races remain** in the model registry (version numbering, promotion), as they did under SQL
  without row locks. Wrap them in Firestore transactions if two operators will promote concurrently.
- **Tenant isolation is application-level**, as before: every query is filtered by the JWT's `hospital_id`.
  Firestore rules cannot do it for you because the services use admin credentials.
- **Model weights are stored as JSON text** (Firestore rejects nested arrays); `has_label` is a derived field kept
  so "labelled records only" is a cheap equality query.
- **Cost model changes**: Firestore bills per document read. Listing endpoints read up to 500 documents; the
  training-status counts use aggregation queries.
- Documents are limited to 1 MiB. Nothing stored here comes close.

## What has and hasn't been verified

Verified: the full test suites of Modules 1, 2, 3, 7, 8 and the root integration tests (real services over HTTP) on
the local store; the Firestore backend's queries/batches built with the real client library (offline); both
migration scripts end to end from a SQLite database created with the old models.

**Not** verified: a run against real Firestore or the emulator (it could not be downloaded where this was built).
Before production, run `FIRESTORE_EMULATOR_HOST=localhost:8080 python -m pytest module1-auth/test_docstore.py`
against `firebase emulators:start --only firestore`, then your own smoke test against a staging project.

## Rolling back

The old SQL code is not in this tree. Keep the Supabase project untouched until verified; to go back, restore
the previous release and point it at the Supabase database (data written to Firestore after the cutover would
need copying back by hand).

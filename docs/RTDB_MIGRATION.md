# Using Firebase Realtime Database instead of Firestore

`FEDHEAL_DB_BACKEND=rtdb` swaps the data layer in Module 1 and Module 7 (`docstore.py`, `RTDBBackend`).
Nothing above `docstore.py` changes. Firestore stays the default in staging/production; opt in explicitly.

## Setup
1. Create a Realtime Database in the Firebase console (pick the region carefully).
2. Service account with access to it (same `GOOGLE_APPLICATION_CREDENTIALS` mechanism as Firestore).
3. Set `FEDHEAL_DB_BACKEND=rtdb` and `FEDHEAL_FIREBASE_DATABASE_URL=https://<project>-default-rtdb.<region>.firebasedatabase.app`.
4. `firebase deploy --only database` (deploys `infra/database.rules.json`: all client access denied, `.indexOn` for the
   equality-filter fields). Without the indexes queries still return correct results but download the whole collection.
5. Local emulator: `firebase emulators:start --only database`, then `FIREBASE_DATABASE_EMULATOR_HOST=localhost:9000`
   (refused when `FEDHEAL_ENV=production`).

## Differences from Firestore you should know about
- **Not atomic across documents on a crash.** `create` claims its path with a transaction, then the other ops go out as one
  multi-path update. A conflicting create or a failed write undoes the claims; a process crash in between can leave a
  claimed document (e.g. an e-mail index entry without its user). Firestore's batch has no such window.
- **`update` is not guarded against a concurrent delete** (existence is checked, then the fields are written).
- **Queries**: one server-side equality filter per query; every other filter, the ordering and the limit run in the service.
  Collections are read whole when no equality filter exists. Fine for the current sizes; revisit for large vitals tables.
- **Hospital isolation is still enforced in application code** (`hospital_id` from the JWT), exactly as with Firestore.
  The rules deny every direct client read/write.
- Stored values are encoded (`None`, lists, dicts and datetimes are wrapped) because RTDB drops nulls/empties and turns
  arrays into objects. Do not read or write the database by hand and expect plain values.
- Existing Firestore data is **not** copied automatically.

## Tests
`server/auth/test_docstore_rtdb.py` runs the backend against a strict in-memory fake. It has **not** been run against the
real emulator or service.

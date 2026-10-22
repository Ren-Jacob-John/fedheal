"""
Database setup — Firestore (Firebase) in staging/production, a local JSON-file
store for development and tests. See docstore.py for the why and the rules.

Backend selection (FEDHEAL_DB_BACKEND):
  unset in development/test  -> local JSON file (FEDHEAL_LOCAL_STORE_PATH, default ./fedheal_auth_store.json)
  unset in staging/production-> firestore
  firestore | local | memory -> explicit; local/memory are refused outside development/test

Firestore settings:
  FEDHEAL_FIREBASE_PROJECT_ID   required (unless FIRESTORE_EMULATOR_HOST is set)
  FEDHEAL_FIRESTORE_DATABASE    optional named database, default "(default)"
  GOOGLE_APPLICATION_CREDENTIALS path to a service-account key, or run with an attached service account
  FIRESTORE_EMULATOR_HOST       e.g. localhost:8080 — talk to the Firebase emulator instead

Every document carries hospital_id, and every query filters by the JWT's
hospital_id in application code (repo.py / the endpoints), so tenant isolation
holds regardless of backend. There are no schema migrations: documents are
created on first write and indexes live in firestore.indexes.json.
"""
import config
from dotenv import load_dotenv

from docstore import make_backend
from repo import Repo

load_dotenv()  # picks up .env in this folder if present

backend = make_backend(local_default_path="./fedheal_auth_store.json",
                       is_local=config.is_local(), env=config.current_env())
repo = Repo(backend)


def get_db() -> Repo:
    """FastAPI dependency (name kept from the SQL version): the module's repository."""
    return repo

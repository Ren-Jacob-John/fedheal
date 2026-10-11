"""
Database for the Admin/Platform module's OWN data only: training-round
history, validation-flag summaries and the model registry. Firestore in
staging/production, a local JSON-file store for development — see
docstore.py for the backend rules and module1-auth/database.py's docstring
for the environment variables (they are identical here).

Deliberately does NOT store a copy of the hospitals collection — hospital
identity/status lives in Module 1 and Module 7 always asks Module 1 for the
current truth (see hospitals_client.py). Duplicating it here would create a
second source of truth that can drift out of sync.

Module 7 may share a Firebase project (and even the default database) with
Module 1: the collection names don't collide. Set FEDHEAL_ADMIN_FIRESTORE_DATABASE
to give this service a named database of its own.
"""
import os

import config
from dotenv import load_dotenv

from docstore import make_backend
from repo import Repo

load_dotenv()  # picks up .env in this folder if present

if os.environ.get("FEDHEAL_ADMIN_FIRESTORE_DATABASE", "").strip():
    os.environ["FEDHEAL_FIRESTORE_DATABASE"] = os.environ["FEDHEAL_ADMIN_FIRESTORE_DATABASE"].strip()

backend = make_backend(local_default_path="./fedheal_admin_store.json",
                       is_local=config.is_local(), env=config.current_env())
repo = Repo(backend)


def get_db() -> Repo:
    """FastAPI dependency (name kept from the SQL version): the module's repository."""
    return repo

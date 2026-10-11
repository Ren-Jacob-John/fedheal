"""Test-suite environment: local tier, so config.py's dev-only fallbacks apply.
(Staging/production behaviour is exercised explicitly in test_config.py by
running fresh interpreters with FEDHEAL_ENV set.)

Storage: one throwaway JSON-file document store shared by every test module in
the session (and by the helper scripts some tests run as subprocesses, e.g.
create_super_admin.py). It never touches fedheal_auth_store.json or Firestore."""
import os
import shutil
import tempfile

os.environ["FEDHEAL_ENV"] = "development"
_STORE_DIR = tempfile.mkdtemp(prefix="fedheal-m1-test-")
os.environ["FEDHEAL_DB_BACKEND"] = "local"
os.environ["FEDHEAL_LOCAL_STORE_PATH"] = os.path.join(_STORE_DIR, "store.json")


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_STORE_DIR, ignore_errors=True)

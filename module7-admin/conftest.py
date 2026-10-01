"""Test-suite environment: local tier, so config.py's dev-only fallbacks apply.
(Staging/production behaviour is exercised explicitly in test_config.py by
running fresh interpreters with FEDHEAL_ENV set.)"""
import os

os.environ["FEDHEAL_ENV"] = "development"
import tempfile  # noqa: E402

# Throwaway DB so tests never touch fedheal_admin.db
os.environ.setdefault("FEDHEAL_ADMIN_DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/admin_test.db")

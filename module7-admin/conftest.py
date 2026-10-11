"""Test-suite environment: local tier, so config.py's dev-only fallbacks apply.
(Staging/production behaviour is exercised explicitly in test_config.py by
running fresh interpreters with FEDHEAL_ENV set.)

Storage: the in-memory document store, so tests never touch
fedheal_admin_store.json or Firestore."""
import os

os.environ["FEDHEAL_ENV"] = "development"
os.environ["FEDHEAL_DB_BACKEND"] = "memory"

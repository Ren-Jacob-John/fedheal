"""Test-suite environment: local tier, so config.py's dev-only fallbacks apply.
(Staging/production behaviour is exercised explicitly in test_config.py by
running fresh interpreters with FEDHEAL_ENV set.)"""
import os

os.environ["FEDHEAL_ENV"] = "development"


def pytest_sessionfinish(session, exitstatus):
    """Remove throwaway SQLite files the test modules create in the cwd."""
    import glob

    try:
        import database

        database.engine.dispose()
    except Exception:
        pass
    for path in glob.glob("./_test_*.db"):
        try:
            os.remove(path)
        except OSError:
            pass

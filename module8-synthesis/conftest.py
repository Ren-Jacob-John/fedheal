"""Test-suite environment: local tier, so config.py's dev-only fallbacks apply.
(Staging/production behaviour is exercised explicitly in test_config.py by
running fresh interpreters with FEDHEAL_ENV set.)"""
import os

os.environ["FEDHEAL_ENV"] = "development"
# The demo fallback exists only behind an explicit flag (no implicit dev default); tests that need it say so here.
os.environ["FEDHEAL_ALLOW_DEMO_MODEL"] = "true"

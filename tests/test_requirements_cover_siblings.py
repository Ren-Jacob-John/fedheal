"""Module 8 imports modules 5 and 6 directly, so its requirements.txt must
cover the third-party packages they need at import time. A missing pin here
passes on a developer machine and fails on a clean install (this happened with
lightgbm). Run from the repo root."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
REQUIRED_BY_IMPORT_CHAIN = {"scikit-learn", "xgboost", "lightgbm", "numpy", "pandas", "shap"}


def names(path):
    out = set()
    for line in (ROOT / path).read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            out.add(re.split(r"[=<>\[ ]", line)[0].lower())
    return out


def test_module8_requirements_cover_import_chain():
    missing = REQUIRED_BY_IMPORT_CHAIN - names("module8-synthesis/requirements.txt")
    assert not missing, f"module8-synthesis/requirements.txt is missing: {sorted(missing)}"


def test_every_service_has_a_dockerfile_and_compose_entry():
    compose = (ROOT / "docker-compose.yml").read_text()
    for module in ("module1-auth", "module2-validation", "module3-fedlearning",
                   "module4-dashboard-react", "module7-admin", "module8-synthesis"):
        assert (ROOT / module / "Dockerfile").exists(), module
        assert f"{module}/Dockerfile" in compose, module

"""Hospital admins and doctors can use the API only from the dashboard origin."""
import os

os.environ.update(FEDHEAL_ENV="test", FEDHEAL_DB_BACKEND="memory", FEDHEAL_DASHBOARD_ORIGIN="http://localhost:5173")

import pytest
from fastapi.testclient import TestClient

import auth
import models
from database import repo
from main import app

DASH = {"Origin": "http://localhost:5173"}
PW = "correct-horse-battery"


@pytest.fixture(scope="module")
def accounts():
    h = repo.create_hospital(models.Hospital(name="Web Only Test Hospital"))
    for email, role, hid in (("sa@test.example", models.Role.SUPER_ADMIN, None),
                             ("ha@test.example", models.Role.HOSPITAL_ADMIN, h.id),
                             ("dr@test.example", models.Role.CLINICIAN, h.id)):
        repo.create_user(models.User(email=email, hashed_password=auth.hash_password(PW), role=role, hospital_id=hid))
    return TestClient(app)


def login(c, email, headers=None):
    return c.post("/token", data={"username": email, "password": PW}, headers=headers or {})


@pytest.mark.parametrize("email", ["ha@test.example", "dr@test.example"])
def test_web_only_roles(accounts, email):
    c = accounts
    assert login(c, email).status_code == 403                                   # curl / scripts
    assert login(c, email, {"Origin": "http://evil.example"}).status_code == 403  # other sites
    r = login(c, email, DASH)
    assert r.status_code == 200
    bearer = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert c.get("/me", headers=bearer).status_code == 403                      # token reused outside the website
    assert c.get("/me", headers={**bearer, "Origin": "http://localhost:8001"}).status_code == 403  # /docs page
    assert c.get("/me", headers={**bearer, **DASH}).status_code == 200          # the dashboard


def test_platform_admin_unaffected(accounts):
    r = login(accounts, "sa@test.example")
    assert r.status_code == 200
    assert accounts.get("/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}).status_code == 200


def test_docs_hidden_outside_development():
    import importlib, config
    os.environ["FEDHEAL_ENV"] = "staging"
    try:
        assert not config.api_docs_enabled()
        os.environ["FEDHEAL_ENABLE_API_DOCS"] = "true"
        assert config.api_docs_enabled()
    finally:
        os.environ["FEDHEAL_ENV"] = "test"
        os.environ.pop("FEDHEAL_ENABLE_API_DOCS", None)

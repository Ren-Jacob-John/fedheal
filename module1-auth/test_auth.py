"""
Authentication module test suite.

Focus: the /register privilege-escalation fix. Public registration must
never be able to produce anything but a CLINICIAN, no matter what the
client sends in the request body; creating an administrator must only be
possible through POST /admin/users, and only for an already-authenticated
SUPER_ADMIN.

Uses a throwaway SQLite file per test session (not fedmed_auth.db) so
these tests never touch real data, and builds the schema directly from
the SQLAlchemy models (Base.metadata.create_all) rather than requiring
alembic to be run first — see module1-auth.md's "Database schema" note
about alembic being the source of truth for *deployed* environments;
tests intentionally don't depend on that.

Run:
    pip install -r requirements.txt pytest
    pytest test_auth.py -v
"""
import os
import uuid

import pytest

# Must be set before `database` (and therefore `main`) is imported, since
# database.py reads FEDHEAL_DATABASE_URL at import time.
_TEST_DB_PATH = f"./_test_auth_{uuid.uuid4().hex}.db"
os.environ["FEDHEAL_DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"

import database  # noqa: E402
import models  # noqa: E402

database.Base.metadata.create_all(bind=database.engine)

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app)


@pytest.fixture(autouse=True, scope="session")
def _cleanup_test_db():
    yield
    database.engine.dispose()
    if os.path.exists(_TEST_DB_PATH):
        os.remove(_TEST_DB_PATH)


# ---------- Helpers ----------

def _unique_email(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}@test.fedheal.local"


_bootstrap_super_admin_token: str | None = None


def _super_admin_token_for_setup() -> str:
    """
    POST /hospitals is SUPER_ADMIN-only, so test setup that needs a hospital
    logs in as one — bootstrapped straight through the ORM once per run (the
    same way _seed_super_admin does; there is deliberately no HTTP path for
    creating the first admin).
    """
    global _bootstrap_super_admin_token
    if _bootstrap_super_admin_token is None:
        session = database.SessionLocal()
        try:
            _, _bootstrap_super_admin_token = _seed_super_admin(session)
        finally:
            session.close()
    return _bootstrap_super_admin_token


def _make_hospital(name: str | None = None) -> dict:
    resp = client.post(
        "/hospitals",
        json={"name": name or f"Hospital {uuid.uuid4().hex[:8]}"},
        headers=_auth_headers(_super_admin_token_for_setup()),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _register_clinician(hospital_id: str, email: str | None = None, password: str = "pw12345") -> dict:
    resp = client.post(
        "/register",
        json={"email": email or _unique_email("clinician"), "password": password, "hospital_id": hospital_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _login(email: str, password: str) -> str:
    resp = client.post("/token", data={"username": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _seed_super_admin(db_session) -> tuple[dict, str]:
    """
    Creates a SUPER_ADMIN directly via the ORM (bootstrapping — this is
    exactly the "how does the very first admin get created" problem every
    real deployment has, and it's deliberately NOT solvable through any
    HTTP endpoint; see module1-auth.md / your deployment runbook for how
    that first account actually gets seeded in practice). Returns the
    created user dict and a fresh login token for it.
    """
    email = _unique_email("superadmin")
    password = "supersecret123"
    user = models.User(
        email=email,
        hashed_password=main.auth.hash_password(password),
        role=models.Role.SUPER_ADMIN,
        hospital_id=None,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = _login(email, password)
    return {"id": user.id, "email": email, "role": user.role.value}, token


@pytest.fixture()
def db_session():
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------- 1. Anonymous user cannot create SUPER_ADMIN via /register ----------

def test_anonymous_register_cannot_create_super_admin():
    hospital = _make_hospital()
    email = _unique_email("wannabe-super")
    resp = client.post(
        "/register",
        json={
            "email": email,
            "password": "pw12345",
            "hospital_id": hospital["id"],
            "role": "super_admin",  # attacker-supplied, must be ignored
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "clinician"

    # Confirm the DB agrees with the API response, not just the response
    # shape — the ORM object, not the JSON, is the ground truth.
    db = database.SessionLocal()
    try:
        stored = db.query(models.User).filter(models.User.email == email).first()
        assert stored is not None
        assert stored.role == models.Role.CLINICIAN
    finally:
        db.close()


# ---------- 2. Anonymous user cannot create ADMIN (hospital_admin) via /register ----------

def test_anonymous_register_cannot_create_hospital_admin():
    hospital = _make_hospital()
    email = _unique_email("wannabe-admin")
    resp = client.post(
        "/register",
        json={
            "email": email,
            "password": "pw12345",
            "hospital_id": hospital["id"],
            "role": "hospital_admin",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "clinician"


# ---------- 3. Anonymous registration creates only CLINICIAN (no role field at all) ----------

def test_anonymous_register_default_is_clinician():
    hospital = _make_hospital()
    resp = client.post(
        "/register",
        json={"email": _unique_email("plain"), "password": "pw12345", "hospital_id": hospital["id"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "clinician"


def test_register_schema_has_no_role_field():
    # Belt-and-suspenders: assert the public schema itself never exposes
    # role, so this can't silently regress if someone edits UserRegister.
    assert "role" not in main.UserRegister.model_fields


# ---------- 4. SUPER_ADMIN can create another administrator via the protected endpoint ----------

def test_super_admin_can_create_hospital_admin(db_session):
    _, super_token = _seed_super_admin(db_session)
    hospital = _make_hospital()
    email = _unique_email("new-hospital-admin")

    resp = client.post(
        "/admin/users",
        json={"email": email, "password": "pw12345", "role": "hospital_admin", "hospital_id": hospital["id"]},
        headers=_auth_headers(super_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "hospital_admin"
    assert body["hospital_id"] == hospital["id"]


def test_super_admin_can_create_another_super_admin(db_session):
    _, super_token = _seed_super_admin(db_session)
    email = _unique_email("new-super-admin")

    resp = client.post(
        "/admin/users",
        json={"email": email, "password": "pw12345", "role": "super_admin"},
        headers=_auth_headers(super_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "super_admin"

    # The new super admin can actually log in and use their role.
    new_token = _login(email, "pw12345")
    assert new_token


# ---------- 5. CLINICIAN cannot create administrators ----------

def test_clinician_cannot_create_admin_via_protected_endpoint():
    hospital = _make_hospital()
    clinician = _register_clinician(hospital["id"], password="pw12345")
    token = _login(clinician["email"], "pw12345")

    resp = client.post(
        "/admin/users",
        json={"email": _unique_email("escalated"), "password": "pw12345", "role": "hospital_admin", "hospital_id": hospital["id"]},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 403


def test_anonymous_cannot_hit_protected_admin_endpoint():
    hospital = _make_hospital()
    # The shared TestClient keeps a cookie jar like a real browser, and
    # earlier tests in this session have logged in and picked up the
    # httpOnly session cookie (see main.py's /token). Clear it so this
    # request is genuinely unauthenticated rather than accidentally
    # riding an earlier test's session.
    client.cookies.clear()
    resp = client.post(
        "/admin/users",
        json={"email": _unique_email("noauth"), "password": "pw12345", "role": "super_admin", "hospital_id": hospital["id"]},
    )
    assert resp.status_code == 401


# ---------- 6. Hospital users cannot escalate their own role ----------

def test_clinician_cannot_self_escalate_via_register_again():
    """
    Re-posting to /register with the same behavior (spoofed role) as an
    already-registered clinician still can't produce anything but
    clinician — there is no "update my own role" path anywhere in this
    module, self-service or otherwise.
    """
    hospital = _make_hospital()
    email = _unique_email("self-escalate")
    first = client.post(
        "/register",
        json={"email": email, "password": "pw12345", "hospital_id": hospital["id"]},
    )
    assert first.status_code == 200
    assert first.json()["role"] == "clinician"

    # Same email is already registered — this must fail on the duplicate
    # check, not on anything role-related, but confirms there's no path
    # that lets a second request against this email change its role.
    second = client.post(
        "/register",
        json={"email": email, "password": "pw12345", "hospital_id": hospital["id"], "role": "super_admin"},
    )
    assert second.status_code == 400  # "Email already registered"

    db = database.SessionLocal()
    try:
        stored = db.query(models.User).filter(models.User.email == email).first()
        assert stored.role == models.Role.CLINICIAN
    finally:
        db.close()


def test_hospital_admin_cannot_escalate_self_to_super_admin(db_session):
    """
    Even a legitimate HOSPITAL_ADMIN (created properly, by a SUPER_ADMIN)
    has no endpoint available to promote themselves further.
    """
    _, super_token = _seed_super_admin(db_session)
    hospital = _make_hospital()
    admin_email = _unique_email("real-hospital-admin")
    created = client.post(
        "/admin/users",
        json={"email": admin_email, "password": "pw12345", "role": "hospital_admin", "hospital_id": hospital["id"]},
        headers=_auth_headers(super_token),
    )
    assert created.status_code == 200
    admin_token = _login(admin_email, "pw12345")

    resp = client.post(
        "/admin/users",
        json={"email": _unique_email("self-super"), "password": "pw12345", "role": "super_admin"},
        headers=_auth_headers(admin_token),
    )
    assert resp.status_code == 403


def test_admin_endpoint_rejects_clinician_role():
    """
    /admin/users is for administrators only — attempting to use it to
    create a plain clinician is rejected, keeping the two registration
    paths cleanly separated rather than letting this endpoint become a
    second, differently-guarded way to do what /register already does.
    """
    db = database.SessionLocal()
    try:
        _, super_token = _seed_super_admin(db)
    finally:
        db.close()
    hospital = _make_hospital()

    resp = client.post(
        "/admin/users",
        json={"email": _unique_email("via-admin-endpoint"), "password": "pw12345", "role": "clinician", "hospital_id": hospital["id"]},
        headers=_auth_headers(super_token),
    )
    assert resp.status_code == 400


# ---------- Regression: existing login functionality is unaffected ----------

def test_login_still_works_for_normal_clinician():
    hospital = _make_hospital()
    email = _unique_email("login-check")
    client.post("/register", json={"email": email, "password": "correct-pw", "hospital_id": hospital["id"]})

    good = client.post("/token", data={"username": email, "password": "correct-pw"})
    assert good.status_code == 200
    assert "access_token" in good.json()

    bad = client.post("/token", data={"username": email, "password": "wrong-pw"})
    assert bad.status_code == 401
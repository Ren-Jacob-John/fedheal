"""
P0 security tests for Module 8: authenticated users only, CORS locked down,
synthesis is audited without clinical values.

Run:  pytest test_security.py -v
"""
import json
import logging
import time

import pytest

from fastapi.testclient import TestClient
from jose import jwt

import auth
import main

client = TestClient(main.app)
CASE = {"record_id": "rec-1"}
RECORD = {"id": "rec-1", "patient_ref": "P-1", "age_years": 58, "height_cm": 172, "weight_kg": 80,
          "systolic_bp": 150, "diastolic_bp": 90, "heart_rate_bpm": 100, "medication_count": 2,
          "medication_mg_total": 300, "label": 1, "label_source": "hospital", "validation_status": "passed"}


@pytest.fixture(autouse=True)
def stub_module1(monkeypatch):
    async def fake(record_id, token):
        return dict(RECORD, id=record_id)
    monkeypatch.setattr(main, "fetch_record", fake)


def jwt_for(role="clinician", *, ttl=600, secret=None):
    return jwt.encode({"sub": "user-9", "role": role, "hospital_id": "h1", "exp": int(time.time()) + ttl},
                      secret or auth.SECRET_KEY, algorithm="HS256")


def test_unauthenticated_is_401():
    assert client.post("/synthesize/record", json=CASE).status_code == 401


def test_invalid_expired_forged_are_401():
    for tok in ("garbage", jwt_for(ttl=-5), jwt_for(secret="attacker-secret-attacker-secret-1234")):
        r = client.post("/synthesize/record", json=CASE, headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 401


def test_authenticated_user_proceeds():
    r = client.post("/synthesize/record", json=CASE, headers={"Authorization": f"Bearer {jwt_for()}"})
    assert r.status_code == 200, r.text


def test_cookie_session_proceeds():
    r = client.post("/synthesize/record", json=CASE, cookies={auth.TOKEN_COOKIE_NAME: jwt_for()})
    assert r.status_code == 200


def test_health_open():
    assert client.get("/health").status_code == 200


def test_audit_has_identity_but_no_clinical_values(caplog):  # values must never reach the log
    caplog.set_level(logging.INFO, logger="fedheal.audit")
    client.post("/synthesize/record", json=CASE, headers={"Authorization": f"Bearer {jwt_for()}"})
    ev = [json.loads(r.getMessage()) for r in caplog.records if r.name == "fedheal.audit"][-1]
    assert ev["action"] == "synthesis.run" and ev["actor_user_id"] == "user-9" and ev["hospital_id"] == "h1"
    assert "58" not in json.dumps(ev) and "150" not in json.dumps(ev)
    assert ev["record_id"] == "rec-1"


def test_cors_locked_down():
    ok = client.options("/synthesize/record", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type"})
    assert ok.status_code == 200
    assert {m.strip() for m in ok.headers["access-control-allow-methods"].split(",")} == {"GET", "POST"}
    bad = client.options("/synthesize/record", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bad.headers
    assert client.options("/synthesize/record", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "PUT"}).status_code == 400

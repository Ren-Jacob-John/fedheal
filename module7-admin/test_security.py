"""
P0 security tests for Module 7 (admin): super_admin JWT gate, per-hop
service keys, ReviewDecision-adjacent CORS, audit logging.

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


def jwt_for(role="super_admin", *, ttl=600, secret=None):
    return jwt.encode({"sub": "user-1", "role": role, "hospital_id": None, "exp": int(time.time()) + ttl},
                      secret or auth.SECRET_KEY, algorithm="HS256")


def bearer(t):
    return {"Authorization": f"Bearer {t}"}


ADMIN_GETS = ["/admin/rounds", "/admin/flags"]


@pytest.mark.parametrize("path", ADMIN_GETS)
class TestSuperAdminEndpoints:
    def test_no_credentials_401(self, path):
        assert client.get(path).status_code == 401

    def test_invalid_and_expired_401(self, path):
        assert client.get(path, headers=bearer("garbage")).status_code == 401
        assert client.get(path, headers=bearer(jwt_for(ttl=-5))).status_code == 401
        assert client.get(path, headers=bearer(jwt_for(secret="attacker-secret-attacker-secret-1234"))).status_code == 401

    @pytest.mark.parametrize("role", ["clinician", "hospital_admin"])
    def test_non_super_admin_403(self, path, role):
        assert client.get(path, headers=bearer(jwt_for(role))).status_code == 403

    def test_super_admin_ok(self, path):
        assert client.get(path, headers=bearer(jwt_for())).status_code == 200

    def test_cookie_session_ok(self, path):
        assert client.get(path, cookies={auth.TOKEN_COOKIE_NAME: jwt_for()}).status_code == 200


def test_patch_hospital_requires_super_admin():
    assert client.patch("/admin/hospitals/x", json={"is_active": False}).status_code == 401
    assert client.patch("/admin/hospitals/x", json={"is_active": False},
                        headers=bearer(jwt_for("hospital_admin"))).status_code == 403


def test_trigger_requires_super_admin():
    assert client.post("/admin/rounds/trigger").status_code == 401
    assert client.post("/admin/rounds/trigger", headers=bearer(jwt_for("clinician"))).status_code == 403


class TestServiceKeys:
    FLAG = {"hospital_id": "h1", "status": "flagged", "reason": "bp out of range", "count": 2}
    ROUND = {"round_number": 1, "n_hospitals": 2}

    def test_flags_need_module2_key(self):
        assert client.post("/admin/flags", json=self.FLAG).status_code == 401
        assert client.post("/admin/flags", json=self.FLAG, headers={"X-Service-Key": "iammightythor"}).status_code == 401
        assert client.post("/admin/flags", json=self.FLAG, headers={"X-Service-Key": auth.MODULE3_SERVICE_KEY}).status_code == 401
        ok = client.post("/admin/flags", json=self.FLAG, headers={"X-Service-Key": auth.MODULE2_SERVICE_KEY})
        assert ok.status_code == 200

    def test_rounds_need_module3_key(self):
        assert client.post("/admin/rounds", json=self.ROUND).status_code == 401
        assert client.post("/admin/rounds", json=self.ROUND, headers={"X-Service-Key": "iamgodofdeath"}).status_code == 401
        assert client.post("/admin/rounds", json=self.ROUND, headers={"X-Service-Key": auth.MODULE2_SERVICE_KEY}).status_code == 401
        ok = client.post("/admin/rounds", json=self.ROUND, headers={"X-Service-Key": auth.MODULE3_SERVICE_KEY})
        assert ok.status_code == 200

    def test_user_jwt_is_not_a_service_key(self):
        assert client.post("/admin/flags", json=self.FLAG, headers={"X-Service-Key": jwt_for()}).status_code == 401

    def test_failures_audited_without_key_value(self, caplog):
        caplog.set_level(logging.INFO, logger="fedheal.audit")
        client.post("/admin/flags", json=self.FLAG, headers={"X-Service-Key": "very-secret-wrong-key"})
        ev = [json.loads(r.getMessage()) for r in caplog.records if r.name == "fedheal.audit"]
        assert ev[-1]["action"] == "service_authn.failure" and ev[-1]["actor_service"] == "module2"
        assert "very-secret-wrong-key" not in caplog.text


def test_authz_denial_audited(caplog):
    caplog.set_level(logging.INFO, logger="fedheal.audit")
    client.get("/admin/rounds", headers=bearer(jwt_for("clinician")))
    ev = [json.loads(r.getMessage()) for r in caplog.records if r.name == "fedheal.audit"][-1]
    assert ev["action"] == "authz.denied" and ev["actor_role"] == "clinician"


class TestCors:
    def _pre(self, origin, method):
        return client.options("/admin/rounds", headers={"Origin": origin, "Access-Control-Request-Method": method,
                                                        "Access-Control-Request-Headers": "Authorization"})

    def test_dashboard_origin_allowed_with_explicit_methods(self):
        r = self._pre("http://localhost:5173", "GET")
        assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert {m.strip() for m in r.headers["access-control-allow-methods"].split(",")} == {"GET", "POST", "PATCH"}

    def test_foreign_origin_and_unused_method_refused(self):
        assert "access-control-allow-origin" not in self._pre("https://evil.example", "GET").headers
        assert self._pre("http://localhost:5173", "DELETE").status_code == 400

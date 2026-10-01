"""
P0 security tests for Module 2: /validate/* is internal, callable only with
a hospital-scoped credential minted by Module 1; size limits answer 413.

Run:  pytest test_security.py -v
"""
import io
import json
import logging
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from jose import jwt

import main
import service_auth

client = TestClient(main.app)
KEY = main.VALIDATE_SIGNING_KEY
HOSP = "hospital-a"

GOOD = {"patient_ref": "P-1", "age_years": 50, "height_cm": 170, "weight_kg": 70,
        "systolic_bp": 120, "diastolic_bp": 80, "heart_rate_bpm": 70,
        "medication_count": 0, "medication_mg_total": 0}
CSV_HEADER = "patient_ref,age_years,height_cm,weight_kg,systolic_bp,diastolic_bp,heart_rate_bpm,medication_count,medication_mg_total"


def token(hospital=HOSP, *, caller="module1", audience=service_auth.AUD_VALIDATE, key=None, ttl=60):
    now = int(time.time())
    claims = {"iss": service_auth.ISSUER, "sub": caller, "aud": audience, "iat": now, "exp": now + ttl, "jti": uuid.uuid4().hex}
    if hospital is not None:
        claims["hid"] = hospital
    return jwt.encode(claims, key or KEY, algorithm="HS256")


def h(tok=None):
    return {"X-Service-Key": tok} if tok else {}


def post_json(records, headers=None, **extra):
    return client.post("/validate/vitals", json={"records": records, **extra}, headers=headers or {})


def post_csv(text, headers=None, **form):
    return client.post("/validate/vitals/csv", files={"file": ("v.csv", text.encode(), "text/csv")},
                       data=form, headers=headers or {})


def csv_text(n):
    return CSV_HEADER + "\n" + "\n".join(["P-1,50,170,70,120,80,70,0,0"] * n) + "\n"


ENDPOINTS = [
    ("json", lambda headers=None, **kw: post_json([GOOD], headers, **kw)),
    ("csv", lambda headers=None, **kw: post_csv(csv_text(1), headers, **kw)),
]


@pytest.mark.parametrize("name,call", ENDPOINTS)
class TestServiceAuthentication:
    def test_unauthenticated_is_401(self, name, call):
        assert call().status_code == 401

    def test_garbage_credential_is_401(self, name, call):
        assert call(h("garbage")).status_code == 401

    def test_forged_signature_is_401(self, name, call):
        assert call(h(token(key="attacker-key-attacker-key-attacker-key"))).status_code == 401

    def test_expired_credential_is_401(self, name, call):
        assert call(h(token(ttl=-10))).status_code == 401

    def test_old_static_shared_keys_are_401(self, name, call):
        for old in ("iamgodofthunder", "iammightythor", "dev-only-key-module3-to-module1"):
            assert call(h(old)).status_code == 401

    def test_user_jwt_is_not_accepted(self, name, call):
        user_jwt = jwt.encode({"sub": "u", "role": "super_admin", "exp": int(time.time()) + 600},
                              "dev-only-change-me", algorithm="HS256")
        assert call(h(user_jwt)).status_code == 401
        assert call({"Authorization": f"Bearer {user_jwt}"}).status_code == 401

    def test_valid_token_for_unauthorized_service_is_403(self, name, call):
        assert call(h(token(caller="module3"))).status_code == 403
        assert call(h(token(caller="module5"))).status_code == 403

    def test_valid_token_for_other_endpoint_is_403(self, name, call):
        assert call(h(token(audience=service_auth.AUD_VITALS_EXPORT))).status_code == 403

    def test_token_without_hospital_scope_is_403(self, name, call):
        assert call(h(token(hospital=None))).status_code == 403
        assert call(h(token(hospital="*"))).status_code == 403

    def test_authorized_request_proceeds(self, name, call):
        resp = call(h(token()))
        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 1 and resp.json()["passed"] == 1


class TestTenantBinding:
    def test_matching_body_hospital_id_is_accepted(self):
        assert post_json([GOOD], h(token()), hospital_id=HOSP).status_code == 200

    def test_mismatching_body_hospital_id_is_403(self):
        assert post_json([GOOD], h(token()), hospital_id="hospital-b").status_code == 403

    def test_mismatching_csv_form_hospital_id_is_403(self):
        assert post_csv(csv_text(1), h(token()), hospital_id="hospital-b").status_code == 403

    def test_hospital_id_may_be_omitted_credential_supplies_it(self):
        assert post_json([GOOD], h(token())).status_code == 200


class TestValidationBehaviourUnchanged:
    def test_out_of_range_record_is_flagged_or_rejected(self):
        bad = {**GOOD, "systolic_bp": 900}
        r = post_json([bad], h(token())).json()
        assert r["passed"] == 0 and r["flagged"] + r["rejected"] == 1

    def test_non_csv_filename_is_400(self):
        resp = client.post("/validate/vitals/csv", files={"file": ("v.txt", b"x", "text/plain")}, headers=h(token()))
        assert resp.status_code == 400

    def test_health_stays_open_for_probes(self):
        assert client.get("/health").status_code == 200


class TestSizeLimits:
    def test_small_json_ok(self):
        assert post_json([GOOD] * 3, h(token())).status_code == 200

    def test_max_records_ok_and_one_more_is_413(self):
        n = main.UPLOAD_LIMITS.max_records
        assert post_json([GOOD] * n, h(token())).status_code == 200
        assert post_json([GOOD] * (n + 1), h(token())).status_code == 413

    def test_oversized_json_body_is_413(self):
        body = json.dumps({"records": [GOOD], "pad": "x" * (main.UPLOAD_LIMITS.max_json_body_bytes + 70000)})
        resp = client.post("/validate/vitals", content=body,
                           headers={**h(token()), "Content-Type": "application/json"})
        assert resp.status_code == 413

    def test_oversized_json_without_content_length_is_413(self):
        def chunks():
            for _ in range((main.UPLOAD_LIMITS.max_json_body_bytes + 70000) // 65536 + 2):
                yield b"x" * 65536
        resp = client.post("/validate/vitals", content=chunks(),
                           headers={**h(token()), "Content-Type": "application/json"})
        assert resp.status_code == 413

    def test_csv_ok_at_row_limit_and_413_above(self):
        n = main.UPLOAD_LIMITS.max_records
        assert post_csv(csv_text(n), h(token())).status_code == 200
        assert post_csv(csv_text(n + 1), h(token())).status_code == 413

    def test_oversized_csv_is_413(self):
        text = CSV_HEADER + "\nP-1," + "9" * (main.UPLOAD_LIMITS.max_csv_bytes + 70000) + "\n"
        assert post_csv(text, h(token())).status_code == 413

    def test_oversized_field_is_413(self):
        big = "A" * (main.UPLOAD_LIMITS.max_field_chars + 1)
        assert post_json([{**GOOD, "patient_ref": big}], h(token())).status_code == 413
        assert post_csv(csv_text(1).replace("P-1", big, 1), h(token())).status_code == 413

    def test_auth_is_checked_before_size(self):
        n = main.UPLOAD_LIMITS.max_records
        assert post_json([GOOD] * (n + 1)).status_code == 401


class TestAuditAndCors:
    def _events(self, caplog):
        return [json.loads(r.getMessage()) for r in caplog.records if r.name == "fedheal.audit"]

    def test_failures_and_successes_audited_without_secrets_or_records(self, caplog):
        caplog.set_level(logging.INFO, logger="fedheal.audit")
        tok = token()
        post_json([{**GOOD, "patient_ref": "P-DO-NOT-LOG"}], h(tok))
        post_json([GOOD], h("garbage-credential-value"))
        evs = self._events(caplog)
        assert any(e["action"] == "validate" and e["outcome"] == "success" and e["hospital_id"] == HOSP for e in evs)
        assert any(e["action"] == "service_authn.failure" and e["status_code"] == 401 for e in evs)
        assert tok not in caplog.text and "garbage-credential-value" not in caplog.text
        assert "P-DO-NOT-LOG" not in caplog.text

    def test_cross_tenant_attempt_audited(self, caplog):
        caplog.set_level(logging.INFO, logger="fedheal.audit")
        post_json([GOOD], h(token()), hospital_id="hospital-b")
        assert any(e["action"] == "cross_tenant.attempt" and e["requested_hospital_id"] == "hospital-b"
                   for e in self._events(caplog))

    def test_no_cors_grant_to_browsers(self):
        resp = client.options("/validate/vitals", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
        assert "access-control-allow-origin" not in resp.headers

"""
P0 security tests for Module 7 (admin): super_admin JWT gate, per-hop
service keys, ReviewDecision-adjacent CORS, audit logging.

Run:  pytest test_security.py -v
"""
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

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


ADMIN_GETS = ["/admin/rounds", "/admin/flags", "/admin/retraining/requests"]


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


def svc_token(key, caller, aud, hid):
    import service_auth
    return {"X-Service-Key": service_auth.mint_service_token(key, caller=caller, audience=aud, hospital_id=hid)}


def runner_token(hospital_id):
    import service_auth
    token = service_auth.mint_service_token(
        auth.M3_M7_SIGNING_KEY, caller="module3",
        audience="module7:retraining-runner", hospital_id=hospital_id,
    )
    return {"X-Service-Key": token}


def test_retraining_is_off_by_default(monkeypatch):
    monkeypatch.setenv("FEDHEAL_RETRAIN_MIN_ELIGIBLE_RECORDS", "0")
    response = client.post("/admin/retraining/eligibility", json={"eligible_records": 100},
                          headers=runner_token("retrain-off"))
    assert response.status_code == 200
    assert response.json() == {"status": "disabled", "request_id": None}


def test_retraining_endpoints_reject_unscoped_or_wrong_audience_tokens():
    import service_auth

    assert client.post("/admin/retraining/eligibility", json={"eligible_records": 10}).status_code == 401
    assert client.get("/admin/retraining/requests/next").status_code == 401
    assert client.post("/admin/retraining/requests/complete",
                       json={"request_id": "x", "status": "COMPLETED"}).status_code == 401

    unscoped = service_auth.mint_service_token(
        auth.M3_M7_SIGNING_KEY, caller="module3",
        audience="module7:retraining-runner",
    )
    headers = {"X-Service-Key": unscoped}
    assert client.get("/admin/retraining/requests/next", headers=headers).status_code == 403
    assert client.post("/admin/retraining/eligibility",
                       json={"eligible_records": 10}, headers=headers).status_code == 403

    wrong_audience = svc_token(
        auth.M3_M7_SIGNING_KEY, "module3", service_auth.AUD_MODEL_CANDIDATE, "retrain-wrong-aud",
    )
    assert client.get("/admin/retraining/requests/next", headers=wrong_audience).status_code == 403


def test_retraining_requests_are_thresholded_idempotent_and_hospital_scoped(monkeypatch):
    monkeypatch.setenv("FEDHEAL_RETRAIN_MIN_ELIGIBLE_RECORDS", "2")
    h1, h2 = "retrain-h1", "retrain-h2"
    token1, token2 = runner_token(h1), runner_token(h2)

    baseline = client.post("/admin/retraining/eligibility", json={"eligible_records": 10}, headers=token1)
    assert baseline.status_code == 200 and baseline.json()["status"] == "baseline_initialized"
    below = client.post("/admin/retraining/eligibility", json={"eligible_records": 11}, headers=token1)
    assert below.status_code == 200 and below.json()["status"] == "below_threshold"
    with ThreadPoolExecutor(max_workers=2) as pool:
        schedule_results = list(pool.map(
            lambda count: client.post(
                "/admin/retraining/eligibility", json={"eligible_records": count}, headers=token1,
            ),
            (12, 14),
        ))
    assert all(response.status_code == 200 for response in schedule_results)
    assert sorted(response.json()["status"] for response in schedule_results) == ["already_queued", "queued"]
    queued = next(response for response in schedule_results if response.json()["status"] == "queued")
    duplicate = next(response for response in schedule_results if response.json()["status"] == "already_queued")
    assert queued.json()["request_id"] == duplicate.json()["request_id"]

    assert client.get("/admin/retraining/requests/next", headers=token2).json() is None
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(
            lambda _: client.get("/admin/retraining/requests/next", headers=token1),
            range(2),
        ))
    claimed = [response for response in claims if response.json() is not None]
    assert len(claimed) == 1 and claimed[0].json()["status"] == "CLAIMED"
    assert claimed[0].json()["baseline_records"] == 10
    assert sum(response.json() is None for response in claims) == 1
    more_during_run = client.post(
        "/admin/retraining/eligibility", json={"eligible_records": 15}, headers=token1,
    )
    assert more_during_run.json()["status"] == "already_queued"
    cross_tenant = client.post(
        "/admin/retraining/requests/complete",
        json={"request_id": queued.json()["request_id"], "status": "COMPLETED", "eligible_records": 15},
        headers=token2,
    )
    assert cross_tenant.status_code == 404
    no_candidate = client.post(
        "/admin/retraining/requests/complete",
        json={"request_id": queued.json()["request_id"], "status": "COMPLETED", "eligible_records": 15},
        headers=token1,
    )
    assert no_candidate.status_code == 409

    import service_auth
    candidate = client.post(
        "/admin/models/candidates",
        json={
            "model_name": "networked-vitals",
            "condition": "heart_disease",
            "training_round": 1,
            "participating_hospitals": [h1],
            "training_metadata": {"retraining_request_ids": [queued.json()["request_id"]]},
            "metrics": {},
            "artifact_hash": "a" * 64,
        },
        headers=svc_token(auth.M3_M7_SIGNING_KEY, "module3", service_auth.AUD_MODEL_CANDIDATE, "*"),
    )
    assert candidate.status_code == 201
    assert candidate.json()["deployment_status"] == "CANDIDATE"
    assert candidate.json()["validation_status"] == "PENDING"
    own_candidate = client.get(
        f"/admin/retraining/requests/{queued.json()['request_id']}/candidate",
        headers=token1,
    )
    assert own_candidate.status_code == 200
    assert own_candidate.json()["registered"] is True
    assert own_candidate.json()["candidate_id"] == candidate.json()["id"]
    cross_tenant_candidate = client.get(
        f"/admin/retraining/requests/{queued.json()['request_id']}/candidate",
        headers=token2,
    )
    assert cross_tenant_candidate.status_code == 404

    completed = client.post(
        "/admin/retraining/requests/complete",
        json={"request_id": queued.json()["request_id"], "status": "COMPLETED", "eligible_records": 15},
        headers=token1,
    )
    assert completed.status_code == 200 and completed.json()["status"] == "COMPLETED"
    after_completion = client.post(
        "/admin/retraining/eligibility", json={"eligible_records": 16}, headers=token1,
    )
    assert after_completion.json()["status"] == "below_threshold"
    next_round = client.post(
        "/admin/retraining/eligibility", json={"eligible_records": 17}, headers=token1,
    )
    assert next_round.json()["status"] == "queued"
    assert next_round.json()["request_id"] != queued.json()["request_id"]


def test_retraining_candidate_status_is_hospital_scoped_and_false_until_candidate_registered(monkeypatch):
    monkeypatch.setenv("FEDHEAL_RETRAIN_MIN_ELIGIBLE_RECORDS", "1")
    hospital_id = "candidate-status-hospital"
    token = runner_token(hospital_id)
    client.post("/admin/retraining/eligibility", json={"eligible_records": 1}, headers=token)
    queued = client.post("/admin/retraining/eligibility", json={"eligible_records": 2}, headers=token).json()
    request_id = queued["request_id"]
    claimed = client.get("/admin/retraining/requests/next", headers=token)
    assert claimed.status_code == 200 and claimed.json()["id"] == request_id

    before = client.get(f"/admin/retraining/requests/{request_id}/candidate", headers=token)
    assert before.status_code == 200 and before.json()["registered"] is False
    assert client.get(
        f"/admin/retraining/requests/{request_id}/candidate",
        headers=runner_token("different-hospital"),
    ).status_code == 404


class TestServiceKeys:
    FLAG = {"hospital_id": "h1", "status": "flagged", "reason": "bp out of range", "count": 2}
    ROUND = {"round_number": 1, "n_hospitals": 2}

    def m2(self, hid="h1", aud=None):
        import service_auth
        return svc_token(auth.M2_M7_SIGNING_KEY, "module2", aud or service_auth.AUD_FLAG_REPORT, hid)

    def m3(self, aud=None, hid="*"):
        import service_auth
        return svc_token(auth.M3_M7_SIGNING_KEY, "module3", aud or service_auth.AUD_ROUND_REPORT, hid)

    def test_flags_need_a_module2_token_scoped_to_that_hospital(self):
        assert client.post("/admin/flags", json=self.FLAG).status_code == 401
        assert client.post("/admin/flags", json=self.FLAG, headers={"X-Service-Key": "iammightythor"}).status_code == 401
        # a token signed with another hop's key is forged here
        assert client.post("/admin/flags", json=self.FLAG, headers=self.m3()).status_code == 401
        ok = client.post("/admin/flags", json=self.FLAG, headers=self.m2("h1"))
        assert ok.status_code == 200

    def test_flag_for_another_hospital_is_refused(self):
        r = client.post("/admin/flags", json={**self.FLAG, "hospital_id": "h2"}, headers=self.m2("h1"))
        assert r.status_code == 403

    def test_flag_token_cannot_be_wildcard_or_wrong_audience(self):
        import service_auth
        with pytest.raises(ValueError):
            service_auth.mint_service_token(auth.M2_M7_SIGNING_KEY, caller="module2",
                                            audience=service_auth.AUD_FLAG_REPORT, hospital_id="*")
        wrong = self.m2("h1", aud=service_auth.AUD_ROUND_REPORT)
        assert client.post("/admin/flags", json=self.FLAG, headers=wrong).status_code == 403

    def test_rounds_need_module3_round_token(self):
        import service_auth
        assert client.post("/admin/rounds", json=self.ROUND).status_code == 401
        assert client.post("/admin/rounds", json=self.ROUND, headers={"X-Service-Key": "iamgodofdeath"}).status_code == 401
        assert client.post("/admin/rounds", json=self.ROUND, headers=self.m2()).status_code == 401
        # right key, wrong endpoint family -> authenticated but not authorised
        wrong = self.m3(aud=service_auth.AUD_MODEL_CANDIDATE)
        assert client.post("/admin/rounds", json=self.ROUND, headers=wrong).status_code == 403
        ok = client.post("/admin/rounds", json=self.ROUND, headers=self.m3())
        assert ok.status_code == 200

    def test_expired_service_token_is_rejected(self):
        import service_auth
        tok = service_auth.mint_service_token(auth.M3_M7_SIGNING_KEY, caller="module3",
                                              audience=service_auth.AUD_ROUND_REPORT, hospital_id="*", ttl_seconds=-5)
        assert client.post("/admin/rounds", json=self.ROUND, headers={"X-Service-Key": tok}).status_code == 401

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

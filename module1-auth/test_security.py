"""
P0 security tests for Module 1: hospital administration access, hospital
directory scoping, tenant-scoped service credentials on /vitals/export,
review-decision validation, CORS, and audit logging.

Run:  pytest test_security.py -v
"""
import json
import logging

import pytest

import secsupport as sx  # must be first: it points the app at a throwaway DB before `database` loads
import models  # noqa: E402
import service_auth  # noqa: E402
from secsupport import client, bearer, main  # noqa: E402

AUDIT_LOGGER = "fedheal.audit"


@pytest.fixture(autouse=True)
def _anonymous_client():
    """Login tests leave a session cookie in the shared TestClient's jar;
    without this, later 'anonymous' requests would silently be logged in."""
    client.cookies.clear()
    yield
    client.cookies.clear()


def audit_records(caplog, action=None):
    out = []
    for rec in caplog.records:
        if rec.name == AUDIT_LOGGER:
            event = json.loads(rec.getMessage())
            if action is None or event["action"] == action:
                out.append(event)
    return out


# =====================================================================
# 1. POST /hospitals — SUPER_ADMIN only
# =====================================================================

class TestCreateHospitalAuthorization:
    def _create(self, headers=None, name=None):
        return client.post("/hospitals", json={"name": name or sx.uid("H")}, headers=headers or {})

    def test_unauthenticated_is_401_and_creates_nothing(self):
        before = sx.hospital_count()
        resp = self._create()
        assert resp.status_code == 401
        assert sx.hospital_count() == before

    def test_invalid_jwt_is_401(self):
        before = sx.hospital_count()
        resp = self._create(bearer("not.a.jwt"))
        assert resp.status_code == 401
        assert sx.hospital_count() == before

    def test_jwt_signed_with_wrong_secret_is_401(self):
        uid, _ = sx.make_user(models.Role.SUPER_ADMIN)
        forged = sx.user_token(uid, models.Role.SUPER_ADMIN, None, secret="attacker-controlled-secret-0123456789")
        assert self._create(bearer(forged)).status_code == 401

    def test_expired_jwt_is_401(self):
        uid, _ = sx.make_user(models.Role.SUPER_ADMIN)
        expired = sx.user_token(uid, models.Role.SUPER_ADMIN, None, expires_minutes=-5)
        before = sx.hospital_count()
        assert self._create(bearer(expired)).status_code == 401
        assert sx.hospital_count() == before

    def test_clinician_is_403(self):
        hid = sx.make_hospital_row()
        _, token = sx.make_user(models.Role.CLINICIAN, hid)
        before = sx.hospital_count()
        assert self._create(bearer(token)).status_code == 403
        assert sx.hospital_count() == before

    def test_hospital_admin_is_403(self):
        hid = sx.make_hospital_row()
        _, token = sx.make_user(models.Role.HOSPITAL_ADMIN, hid)
        before = sx.hospital_count()
        assert self._create(bearer(token)).status_code == 403
        assert sx.hospital_count() == before

    def test_super_admin_succeeds(self):
        _, token = sx.make_user(models.Role.SUPER_ADMIN)
        name = sx.uid("Created")
        resp = self._create(bearer(token), name=name)
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == name
        assert resp.json()["requires_label"] is False  # contract unchanged

    def test_super_admin_duplicate_name_still_400(self):
        _, token = sx.make_user(models.Role.SUPER_ADMIN)
        name = sx.uid("Dup")
        assert self._create(bearer(token), name=name).status_code == 200
        assert self._create(bearer(token), name=name).status_code == 400

    def test_cookie_session_of_super_admin_works(self):
        # The browser dashboard authenticates by httpOnly cookie, not header.
        _, token = sx.make_user(models.Role.SUPER_ADMIN)
        resp = client.post("/hospitals", json={"name": sx.uid("Cookie")},
                           cookies={main.TOKEN_COOKIE_NAME: token})
        assert resp.status_code == 200

    def test_creation_is_audited_without_secrets(self, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
        admin_id, token = sx.make_user(models.Role.SUPER_ADMIN)
        assert self._create(bearer(token)).status_code == 200
        events = audit_records(caplog, "hospital.create")
        assert events and events[-1]["outcome"] == "success"
        assert events[-1]["actor_user_id"] == admin_id
        assert token not in caplog.text

    def test_denied_creation_is_audited(self, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
        hid = sx.make_hospital_row()
        uid, token = sx.make_user(models.Role.CLINICIAN, hid)
        assert self._create(bearer(token)).status_code == 403
        denied = audit_records(caplog, "authz.denied")
        assert denied and denied[-1]["actor_user_id"] == uid and denied[-1]["hospital_id"] == hid
        anon = self._create()
        assert anon.status_code == 401
        assert audit_records(caplog, "authn.failure")


# =====================================================================
# 2. GET /hospitals — authenticated directory; service tokens hospital-scoped
# =====================================================================

class TestHospitalDirectory:
    def test_anonymous_is_401(self):
        assert client.get("/hospitals").status_code == 401

    def test_invalid_and_expired_tokens_are_401(self):
        assert client.get("/hospitals", headers=bearer("garbage")).status_code == 401
        uid, _ = sx.make_user(models.Role.SUPER_ADMIN)
        expired = sx.user_token(uid, models.Role.SUPER_ADMIN, None, expires_minutes=-1)
        assert client.get("/hospitals", headers=bearer(expired)).status_code == 401

    def test_super_admin_sees_every_hospital(self):
        a, b = sx.make_hospital_row(), sx.make_hospital_row()
        _, token = sx.make_user(models.Role.SUPER_ADMIN)
        ids = {h["id"] for h in client.get("/hospitals", headers=bearer(token)).json()}
        assert {a, b} <= ids

    @pytest.mark.parametrize("role", [models.Role.CLINICIAN, models.Role.HOSPITAL_ADMIN])
    def test_any_authenticated_user_sees_the_federation_directory(self, role):
        # Documented access model: the federation map lists every hospital.
        a, b = sx.make_hospital_row(), sx.make_hospital_row()
        _, token = sx.make_user(role, a)
        ids = {h["id"] for h in client.get("/hospitals", headers=bearer(token)).json()}
        assert {a, b} <= ids

    def test_directory_exposes_no_patient_or_user_data(self):
        a = sx.make_hospital_row()
        refs = sx.add_vitals(a, 2)
        _, token = sx.make_user(models.Role.CLINICIAN, a)
        text = client.get("/hospitals", headers=bearer(token)).text
        assert not any(r in text for r in refs) and "@" not in text

    def test_response_shape_is_unchanged(self):
        a = sx.make_hospital_row()
        _, token = sx.make_user(models.Role.CLINICIAN, a)
        assert set(client.get("/hospitals", headers=bearer(token)).json()[0]) == {
            "id", "name", "is_active", "requires_label"}

    def test_service_token_scoped_to_one_hospital_sees_only_it(self):
        a, b = sx.make_hospital_row(), sx.make_hospital_row()
        resp = client.get("/hospitals", headers={"X-Service-Key": sx.svc_token(a)})
        assert resp.status_code == 200
        assert [h["id"] for h in resp.json()] == [a]
        assert b not in resp.text

    def test_directory_wildcard_token_sees_all(self):
        a, b = sx.make_hospital_row(), sx.make_hospital_row()
        tok = sx.svc_token(service_auth.ANY_HOSPITAL, audience=service_auth.AUD_HOSPITAL_DIRECTORY)
        ids = {h["id"] for h in client.get("/hospitals", headers={"X-Service-Key": tok}).json()}
        assert {a, b} <= ids

    def test_wildcard_on_export_audience_does_not_widen(self):
        a = sx.make_hospital_row()
        tok = sx.svc_token(service_auth.ANY_HOSPITAL, audience=service_auth.AUD_VITALS_EXPORT)
        assert client.get("/hospitals", headers={"X-Service-Key": tok}).json() == []
        assert a  # (hospital exists, but the token entitles nothing)

    def test_forged_service_token_is_401(self):
        forged = sx.svc_token(sx.make_hospital_row(), key="attacker-key-attacker-key-attacker-key")
        assert client.get("/hospitals", headers={"X-Service-Key": forged}).status_code == 401

    def test_user_jwt_cannot_be_replayed_as_service_credential(self):
        _, token = sx.make_user(models.Role.SUPER_ADMIN)
        assert client.get("/hospitals", headers={"X-Service-Key": token}).status_code == 401

    def test_patch_still_super_admin_only(self):
        hid = sx.make_hospital_row()
        _, clin = sx.make_user(models.Role.CLINICIAN, hid)
        assert client.patch(f"/hospitals/{hid}", json={"is_active": False}, headers=bearer(clin)).status_code == 403
        assert client.patch(f"/hospitals/{hid}", json={"is_active": False}).status_code == 401
        _, admin = sx.make_user(models.Role.SUPER_ADMIN)
        assert client.patch(f"/hospitals/{hid}", json={"is_active": False}, headers=bearer(admin)).status_code == 200


# =====================================================================
# 3. GET /vitals/export — hospital-scoped service credential
# =====================================================================

@pytest.fixture()
def two_hospitals():
    a, b = sx.make_hospital_row(), sx.make_hospital_row()
    return {"a": a, "b": b, "refs_a": set(sx.add_vitals(a, 4)), "refs_b": set(sx.add_vitals(b, 5))}


def export(hospital_id=None, token=None, params=None, headers=None):
    p = dict(params or {})
    if hospital_id is not None:
        p["hospital_id"] = hospital_id
    h = dict(headers or {})
    if token is not None:
        h["X-Service-Key"] = token
    return client.get("/vitals/export", params=p, headers=h)


class TestExportTenantIsolation:
    def test_credential_for_a_can_export_a(self, two_hospitals):
        resp = export(two_hospitals["a"], sx.svc_token(two_hospitals["a"]))
        assert resp.status_code == 200, resp.text
        assert {r["patient_ref"] for r in resp.json()} == two_hospitals["refs_a"]

    def test_credential_for_a_cannot_export_b(self, two_hospitals):
        resp = export(two_hospitals["b"], sx.svc_token(two_hospitals["a"]))
        assert resp.status_code == 403
        assert not any(ref in resp.text for ref in two_hospitals["refs_b"])

    def test_cross_tenant_attempt_is_audited_without_leaking_token(self, two_hospitals, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
        token = sx.svc_token(two_hospitals["a"])
        export(two_hospitals["b"], token)
        ev = audit_records(caplog, "vitals.export")[-1]
        assert ev["outcome"] == "denied" and ev["reason"] == "cross_tenant"
        assert ev["requested_hospital_id"] == two_hospitals["b"] and ev["token_hospital_id"] == two_hospitals["a"]
        assert token not in caplog.text

    def test_success_is_audited_with_count_only(self, two_hospitals, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
        export(two_hospitals["a"], sx.svc_token(two_hospitals["a"]))
        ev = audit_records(caplog, "vitals.export")[-1]
        assert ev["outcome"] == "success" and ev["count"] == 4 and ev["hospital_id"] == two_hospitals["a"]
        assert not any(ref in caplog.text for ref in two_hospitals["refs_a"])  # no patient data in logs

    def test_missing_credential_is_401(self, two_hospitals):
        assert export(two_hospitals["a"]).status_code == 401

    def test_missing_credential_and_missing_param_is_401(self):
        assert client.get("/vitals/export").status_code == 401

    def test_invalid_credentials_are_401(self, two_hospitals):
        a = two_hospitals["a"]
        for bad in (
            "garbage",
            "iamgodofthunder",                                   # the old hard-coded shared key
            "dev-only-key-module3-to-module1",                   # the old dev fallback
            sx.svc_token(a, key="attacker-key-attacker-key-attacker-key"),  # forged signature
            sx.svc_token(a, ttl=-30),                            # expired
        ):
            assert export(a, bad).status_code == 401, bad

    def test_user_jwt_is_not_a_service_credential(self, two_hospitals):
        _, admin = sx.make_user(models.Role.SUPER_ADMIN)
        a = two_hospitals["a"]
        assert export(a, admin).status_code == 401
        assert export(a, headers=bearer(admin)).status_code == 401  # bearer header alone is not accepted either

    def test_valid_credential_for_wrong_service_or_endpoint_is_403(self, two_hospitals):
        a = two_hospitals["a"]
        assert export(a, sx.svc_token(a, caller="module9")).status_code == 403
        assert export(a, sx.svc_token(a, audience=service_auth.AUD_VALIDATE)).status_code == 403

    def test_no_all_hospitals_export_credential_exists(self, two_hospitals):
        wildcard = sx.svc_token(service_auth.ANY_HOSPITAL, audience=service_auth.AUD_VITALS_EXPORT)
        for hid in (two_hospitals["a"], two_hospitals["b"], service_auth.ANY_HOSPITAL):
            assert export(hid, wildcard).status_code == 403
        with pytest.raises(ValueError):
            service_auth.mint_service_token("k" * 40, caller="module3", audience=service_auth.AUD_VITALS_EXPORT,
                                            hospital_id=service_auth.ANY_HOSPITAL)

    def test_token_without_hospital_scope_is_refused(self, two_hospitals):
        assert export(two_hospitals["a"], sx.svc_token(None)).status_code == 403

    # ---- no leakage through alternate parameters -----------------------

    def test_duplicate_hospital_id_params_cannot_smuggle_another_tenant(self, two_hospitals):
        a, b = two_hospitals["a"], two_hospitals["b"]
        tok = sx.svc_token(a)
        for query in (f"hospital_id={a}&hospital_id={b}", f"hospital_id={b}&hospital_id={a}"):
            resp = client.get(f"/vitals/export?{query}", headers={"X-Service-Key": tok})
            assert resp.status_code in (200, 403)
            assert not any(ref in resp.text for ref in two_hospitals["refs_b"])
            if resp.status_code == 200:
                assert {r["patient_ref"] for r in resp.json()} <= two_hospitals["refs_a"]

    def test_alternate_parameter_names_are_ignored(self, two_hospitals):
        a, b = two_hospitals["a"], two_hospitals["b"]
        tok = sx.svc_token(a)
        # Only alternates, no hospital_id -> rejected, nothing returned
        for alt in ("hospitalId", "hospital", "tenant_id", "hospital_ids", "hid"):
            resp = client.get("/vitals/export", params={alt: b}, headers={"X-Service-Key": tok})
            assert resp.status_code == 422
            assert not any(ref in resp.text for ref in two_hospitals["refs_b"])
        # Alternates alongside the real one -> still exactly A's data
        resp = client.get(
            "/vitals/export",
            params={"hospital_id": a, "hospital": b, "tenant_id": b, "hospitalId": b},
            headers={"X-Service-Key": tok, "X-Hospital-Id": b},
        )
        assert resp.status_code == 200
        assert {r["patient_ref"] for r in resp.json()} == two_hospitals["refs_a"]

    def test_filter_flags_cannot_widen_scope(self, two_hospitals):
        a = two_hospitals["a"]
        resp = export(a, sx.svc_token(a), params={"include_flagged": "true", "labeled_only": "false"})
        assert resp.status_code == 200
        assert {r["patient_ref"] for r in resp.json()} <= two_hospitals["refs_a"]

    @pytest.mark.parametrize("payload", ["' OR '1'='1", "%", "*", "", " ", "A" * 300])
    def test_hostile_hospital_id_values_are_403_not_data(self, two_hospitals, payload):
        resp = export(payload, sx.svc_token(two_hospitals["a"]))
        assert resp.status_code in (403, 422)
        assert resp.text.count("patient_ref") == 0

    def test_hospital_id_case_or_whitespace_variants_do_not_match(self, two_hospitals):
        a = two_hospitals["a"]
        tok = sx.svc_token(a)
        for variant in (a.upper(), f" {a}", f"{a} ", f"{a}%00"):
            if variant == a:
                continue
            assert export(variant, tok).status_code == 403

    def test_legacy_static_key_setting_grants_nothing(self, two_hospitals, monkeypatch):
        monkeypatch.setenv("FEDHEAL_SVC_KEY_M3_M1", "iamgodofthunder")
        assert export(two_hospitals["a"], "iamgodofthunder").status_code == 401


# =====================================================================
# 4. Review decision validation
# =====================================================================

class TestReviewDecision:
    def _setup(self):
        hid = sx.make_hospital_row()
        _, token = sx.make_user(models.Role.HOSPITAL_ADMIN, hid)
        return hid, sx.add_flagged_record(hid), token

    def test_approve_succeeds(self):
        _, rid, token = self._setup()
        resp = client.post(f"/vitals/{rid}/review", json={"decision": "approve"}, headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json() == {"id": rid, "validation_status": "passed"}
        assert sx.record_status(rid) == "passed"

    def test_reject_succeeds_and_deletes(self):
        _, rid, token = self._setup()
        resp = client.post(f"/vitals/{rid}/review", json={"decision": "reject"}, headers=bearer(token))
        assert resp.status_code == 200
        assert resp.json() == {"id": rid, "deleted": True}
        assert not sx.record_exists(rid)

    @pytest.mark.parametrize("bad", ["maybe", "APPROVE", "Approve", "approved", "delete", "", " approve", None, 1, ["approve"]])
    def test_invalid_decision_is_422_and_changes_nothing(self, bad):
        _, rid, token = self._setup()
        resp = client.post(f"/vitals/{rid}/review", json={"decision": bad}, headers=bearer(token))
        assert resp.status_code == 422
        assert sx.record_status(rid) == "flagged"

    def test_missing_decision_is_422(self):
        _, rid, token = self._setup()
        assert client.post(f"/vitals/{rid}/review", json={}, headers=bearer(token)).status_code == 422

    def test_clinician_cannot_review(self):
        hid, rid, _ = self._setup()
        _, clin = sx.make_user(models.Role.CLINICIAN, hid)
        assert client.post(f"/vitals/{rid}/review", json={"decision": "approve"}, headers=bearer(clin)).status_code == 403
        assert sx.record_status(rid) == "flagged"

    def test_admin_of_other_hospital_gets_403_and_audit(self, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
        _, rid, _ = self._setup()
        other = sx.make_hospital_row()
        uid, other_admin = sx.make_user(models.Role.HOSPITAL_ADMIN, other)
        resp = client.post(f"/vitals/{rid}/review", json={"decision": "reject"}, headers=bearer(other_admin))
        assert resp.status_code == 403
        assert sx.record_exists(rid)
        ev = audit_records(caplog, "cross_tenant.attempt")[-1]
        assert ev["actor_user_id"] == uid and ev["hospital_id"] == other

    def test_review_is_audited(self, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
        hid, rid, token = self._setup()
        client.post(f"/vitals/{rid}/review", json={"decision": "approve"}, headers=bearer(token))
        ev = audit_records(caplog, "vitals.review")[-1]
        assert ev["decision"] == "approve" and ev["record_id"] == rid and ev["hospital_id"] == hid

    def test_review_schema_advertises_the_constrained_values(self):
        schema = main.ReviewDecision.model_json_schema()
        assert schema["properties"]["decision"]["enum"] == ["approve", "reject"]


# =====================================================================
# 5. Login audit — no credentials in the log
# =====================================================================

class TestLoginAudit:
    def test_failed_login_logs_hash_not_identity_or_password(self, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
        email = f"{sx.uid('nobody')}@test.fedheal.local"
        resp = client.post("/token", data={"username": email, "password": "Sup3r-secret-guess"})
        assert resp.status_code == 401
        ev = audit_records(caplog, "login")[-1]
        assert ev["outcome"] == "failure" and len(ev["username_hash"]) == 12
        assert email not in caplog.text and "Sup3r-secret-guess" not in caplog.text

    def test_successful_login_logs_user_id_but_not_token(self, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
        hid = sx.make_hospital_row()
        email = f"{sx.uid('ok')}@test.fedheal.local"
        client.post("/register", json={"email": email, "password": "pw-for-audit-test", "hospital_id": hid})
        resp = client.post("/token", data={"username": email, "password": "pw-for-audit-test"})
        assert resp.status_code == 200
        ev = audit_records(caplog, "login")[-1]
        assert ev["outcome"] == "success" and ev["hospital_id"] == hid and ev["actor_role"] == "clinician"
        assert resp.json()["access_token"] not in caplog.text
        assert "pw-for-audit-test" not in caplog.text and email not in caplog.text


# =====================================================================
# 6. CORS
# =====================================================================

class TestCors:
    def _preflight(self, origin, method, headers="Authorization, Content-Type"):
        return client.options("/hospitals", headers={
            "Origin": origin, "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers})

    def test_allowed_origin_method_and_headers(self):
        resp = self._preflight(sx.DEFAULT_ORIGIN, "POST")
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == sx.DEFAULT_ORIGIN
        assert resp.headers["access-control-allow-credentials"] == "true"

    def test_no_wildcards_and_no_unused_methods_advertised(self):
        resp = self._preflight(sx.DEFAULT_ORIGIN, "GET")
        assert resp.headers["access-control-allow-origin"] != "*"
        allowed = {m.strip() for m in resp.headers["access-control-allow-methods"].split(",")}
        assert allowed == {"GET", "POST", "PATCH", "PUT"}   # PUT: case medical-history upsert
        assert "*" not in resp.headers.get("access-control-allow-headers", "")

    @pytest.mark.parametrize("method", ["DELETE"])
    def test_unused_methods_are_refused(self, method):
        assert self._preflight(sx.DEFAULT_ORIGIN, method).status_code == 400

    def test_unexpected_request_header_is_refused(self):
        assert self._preflight(sx.DEFAULT_ORIGIN, "POST", "Authorization, X-Evil").status_code == 400

    def test_foreign_origin_gets_no_cors_grant(self):
        resp = self._preflight("https://evil.example", "POST")
        assert "access-control-allow-origin" not in resp.headers
        resp = client.get("/health", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in resp.headers


# =====================================================================
# 7. Stored-record read access (dashboard picker + Module 8)
# =====================================================================

class TestRecordReadAccess:
    def test_list_requires_authentication(self):
        assert client.get("/vitals").status_code == 401
        assert client.get("/vitals", headers=bearer("garbage")).status_code == 401

    def test_list_returns_only_own_hospital_and_no_other_tenant_data(self):
        a, b = sx.make_hospital_row(), sx.make_hospital_row()
        refs_a, refs_b = sx.add_vitals(a, 3), sx.add_vitals(b, 4)
        _, token = sx.make_user(models.Role.CLINICIAN, a)
        resp = client.get("/vitals", headers=bearer(token))
        assert resp.status_code == 200
        got = {r["patient_ref"] for r in resp.json()}
        assert got == set(refs_a) and not got & set(refs_b)
        assert not any(ref in resp.text for ref in refs_b)

    def test_list_hospital_comes_from_jwt_not_a_parameter(self):
        a, b = sx.make_hospital_row(), sx.make_hospital_row()
        sx.add_vitals(a, 1)
        refs_b = sx.add_vitals(b, 2)
        _, token = sx.make_user(models.Role.CLINICIAN, a)
        resp = client.get("/vitals", params={"hospital_id": b, "hospital": b}, headers=bearer(token))
        assert not any(ref in resp.text for ref in refs_b)

    def test_list_status_filter_and_limit(self):
        a = sx.make_hospital_row()
        sx.add_vitals(a, 3, status="passed")
        sx.add_vitals(a, 2, status="flagged")
        _, token = sx.make_user(models.Role.CLINICIAN, a)
        flagged = client.get("/vitals", params={"validation_status": "flagged"}, headers=bearer(token)).json()
        assert len(flagged) == 2 and {r["validation_status"] for r in flagged} == {"flagged"}
        assert len(client.get("/vitals", params={"limit": 1}, headers=bearer(token)).json()) == 1
        assert client.get("/vitals", params={"validation_status": "bogus"}, headers=bearer(token)).status_code == 422

    def test_super_admin_without_a_hospital_cannot_list(self):
        _, token = sx.make_user(models.Role.SUPER_ADMIN)
        assert client.get("/vitals", headers=bearer(token)).status_code == 400

    def test_get_own_record_returns_the_stored_fields(self):
        a = sx.make_hospital_row()
        ref = sx.add_vitals(a, 1)[0]
        _, token = sx.make_user(models.Role.CLINICIAN, a)
        rid = client.get("/vitals", headers=bearer(token)).json()[0]["id"]
        resp = client.get(f"/vitals/{rid}", headers=bearer(token))
        assert resp.status_code == 200 and resp.json()["patient_ref"] == ref
        assert set(resp.json()) == {"id", "patient_ref", "age_years", "height_cm", "weight_kg", "systolic_bp",
                                    "diastolic_bp", "heart_rate_bpm", "medication_count", "medication_mg_total",
                                    "label", "label_source", "validation_status"}

    def test_get_other_hospitals_record_is_403_and_audited(self, caplog):
        caplog.set_level(logging.INFO, logger=AUDIT_LOGGER)
        a, b = sx.make_hospital_row(), sx.make_hospital_row()
        sx.add_vitals(b, 1)
        _, tok_b = sx.make_user(models.Role.CLINICIAN, b)
        rid = client.get("/vitals", headers=bearer(tok_b)).json()[0]["id"]
        uid, tok_a = sx.make_user(models.Role.CLINICIAN, a)
        resp = client.get(f"/vitals/{rid}", headers=bearer(tok_a))
        assert resp.status_code == 403 and "patient_ref" not in resp.text
        ev = audit_records(caplog, "cross_tenant.attempt")[-1]
        assert ev["actor_user_id"] == uid and ev["record_id"] == rid and ev["target_hospital_id"] == b

    def test_get_missing_is_404_and_anonymous_is_401(self):
        a = sx.make_hospital_row()
        _, token = sx.make_user(models.Role.CLINICIAN, a)
        assert client.get("/vitals/does-not-exist", headers=bearer(token)).status_code == 404
        assert client.get("/vitals/anything").status_code == 401

    def test_fixed_vitals_paths_still_win_over_the_id_pattern(self):
        a = sx.make_hospital_row()
        _, token = sx.make_user(models.Role.CLINICIAN, a)
        assert client.get("/vitals/flagged", headers=bearer(token)).status_code == 200
        assert client.get("/vitals/export").status_code in (401, 422)   # service endpoint, not a record id

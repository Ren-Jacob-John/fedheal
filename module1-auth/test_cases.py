"""
P0 tests: doctor management, patient cases, medical history, case-linked
vitals, clinician review, and hospital isolation across all of them.
Module 2 is replaced by a stub (its own behaviour is tested in module2-validation/).
All data here is synthetic.
"""
import logging

import pytest

import secsupport as sx  # must be first: throwaway DB before `database` loads
import models
from secsupport import client, bearer, main

GOOD = {"age_years": 55, "height_cm": 172, "weight_kg": 80, "systolic_bp": 130,
        "diastolic_bp": 85, "heart_rate_bpm": 72, "medication_count": 1, "medication_mg_total": 50}


@pytest.fixture(autouse=True)
def _fresh_cookies():
    client.cookies.clear()
    yield
    client.cookies.clear()


class _Resp:
    def __init__(self, status):
        self._s = status

    def raise_for_status(self):
        pass

    def json(self):
        return {"total": 1, "passed": int(self._s == "passed"), "flagged": 0,
                "rejected": int(self._s == "rejected"),
                "results": [{"patient_ref": "x", "status": self._s,
                             "reasons": ["systolic_bp out of range"] if self._s == "rejected" else []}]}


def _fake_m2(status):
    class Fake:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None, **k):
            return _Resp(status)
    return Fake


@pytest.fixture
def world():
    ha, hb = sx.make_hospital_row(), sx.make_hospital_row()
    w = {"ha": ha, "hb": hb}
    w["admin_a_id"], w["admin_a"] = sx.make_user(models.Role.HOSPITAL_ADMIN, ha)
    w["admin_b_id"], w["admin_b"] = sx.make_user(models.Role.HOSPITAL_ADMIN, hb)
    w["doc_a_id"], w["doc_a"] = sx.make_user(models.Role.CLINICIAN, ha)
    w["doc_b_id"], w["doc_b"] = sx.make_user(models.Role.CLINICIAN, hb)
    w["super_id"], w["super"] = sx.make_user(models.Role.SUPER_ADMIN, None)
    return w


def _case(token, ref="PAT-DEMO-001", **extra):
    body = {"patient_ref": ref, "admission_reason": "Chest discomfort (synthetic)",
            "current_condition": "heart_disease", "presenting_symptoms": ["chest pain"], **extra}
    return client.post("/cases", json=body, headers=bearer(token))


# ---------------- doctor management ----------------

class TestDoctors:
    def test_hospital_admin_creates_doctor_in_own_hospital_only(self, world):
        r = client.post("/hospital/doctors", headers=bearer(world["admin_a"]),
                        json={"full_name": "Dr Demo", "email": f"{sx.uid('doc')}@demo.local",
                              "password": "long-demo-password"})
        assert r.status_code == 201
        body = r.json()
        assert body["hospital_id"] == world["ha"] and body["role"] == "clinician" and body["is_active"] is True
        assert "password" not in body and "hashed_password" not in body

    def test_cannot_create_doctor_for_another_hospital(self, world):
        r = client.post("/hospital/doctors", headers=bearer(world["admin_a"]),
                        json={"full_name": "Dr X", "email": f"{sx.uid('doc')}@demo.local",
                              "password": "long-demo-password", "hospital_id": world["hb"]})
        assert r.status_code == 403

    def test_own_hospital_id_in_body_is_accepted_but_not_trusted(self, world):
        r = client.post("/hospital/doctors", headers=bearer(world["admin_a"]),
                        json={"full_name": "Dr Y", "email": f"{sx.uid('doc')}@demo.local",
                              "password": "long-demo-password", "hospital_id": world["ha"]})
        assert r.status_code == 201 and r.json()["hospital_id"] == world["ha"]

    @pytest.mark.parametrize("who", ["doc_a", "super"])
    def test_only_hospital_admin_may_create_doctors(self, world, who):
        r = client.post("/hospital/doctors", headers=bearer(world[who]),
                        json={"full_name": "D", "email": f"{sx.uid('doc')}@demo.local",
                              "password": "long-demo-password"})
        assert r.status_code == 403

    def test_anonymous_cannot_create_doctors(self):
        assert client.post("/hospital/doctors", json={}).status_code == 401

    def test_short_password_rejected(self, world):
        r = client.post("/hospital/doctors", headers=bearer(world["admin_a"]),
                        json={"full_name": "D", "email": f"{sx.uid('doc')}@demo.local", "password": "short"})
        assert r.status_code == 422

    def test_admin_lists_only_own_hospitals_doctors(self, world):
        r = client.get("/hospital/doctors", headers=bearer(world["admin_a"]))
        ids = {d["id"] for d in r.json()}
        assert world["doc_a_id"] in ids and world["doc_b_id"] not in ids

    def test_admin_cannot_disable_other_hospitals_doctor(self, world):
        r = client.patch(f"/hospital/doctors/{world['doc_b_id']}", json={"is_active": False},
                         headers=bearer(world["admin_a"]))
        assert r.status_code == 403

    def test_disabled_doctor_cannot_login_or_use_existing_token(self, world):
        email = f"{sx.uid('doc')}@demo.local"
        client.post("/hospital/doctors", headers=bearer(world["admin_a"]),
                    json={"full_name": "Dr Z", "email": email, "password": "long-demo-password"})
        login = client.post("/token", data={"username": email, "password": "long-demo-password"})
        assert login.status_code == 200
        token = login.json()["access_token"]
        client.cookies.clear()
        assert client.get("/me", headers=bearer(token)).status_code == 200
        did = client.get("/me", headers=bearer(token)).json()["id"]
        assert client.patch(f"/hospital/doctors/{did}", json={"is_active": False},
                            headers=bearer(world["admin_a"])).status_code == 200
        assert client.get("/me", headers=bearer(token)).status_code == 401
        assert client.post("/token", data={"username": email, "password": "long-demo-password"}).status_code == 401


# ---------------- cases + isolation ----------------

class TestCases:
    def test_doctor_creates_case_scoped_to_own_hospital(self, world):
        r = _case(world["doc_a"])
        assert r.status_code == 201
        c = r.json()
        assert c["hospital_id"] == world["ha"] and c["created_by"] == world["doc_a_id"]
        assert c["status"] == "OPEN" and c["encounter_id"]

    def test_hospital_id_in_body_is_ignored(self, world):
        r = _case(world["doc_a"], hospital_id=world["hb"])
        assert r.status_code == 201 and r.json()["hospital_id"] == world["ha"]

    def test_invalid_patient_ref_and_missing_reason(self, world):
        assert _case(world["doc_a"], ref="Jane Doe <script>").status_code == 422
        r = client.post("/cases", json={"patient_ref": "PAT-1"}, headers=bearer(world["doc_a"]))
        assert r.status_code == 422

    def test_isolation_matrix(self, world):
        ca = _case(world["doc_a"], "PAT-A-1").json()["id"]
        cb = _case(world["doc_b"], "PAT-B-1").json()["id"]
        # A -> A allowed, B -> B allowed
        assert client.get(f"/cases/{ca}", headers=bearer(world["doc_a"])).status_code == 200
        assert client.get(f"/cases/{cb}", headers=bearer(world["doc_b"])).status_code == 200
        # A -> B denied, B -> A denied, on every case sub-resource
        for path in ("", "/history", "/vitals", "/reviews"):
            assert client.get(f"/cases/{cb}{path}", headers=bearer(world["doc_a"])).status_code == 403, path
            assert client.get(f"/cases/{ca}{path}", headers=bearer(world["doc_b"])).status_code == 403, path
        assert client.patch(f"/cases/{cb}", json={"admission_reason": "x"},
                            headers=bearer(world["doc_a"])).status_code == 403
        assert client.put(f"/cases/{cb}/history", json={}, headers=bearer(world["doc_a"])).status_code == 403
        assert client.post(f"/cases/{cb}/review", json={"decision": "ACCEPTED"},
                           headers=bearer(world["doc_a"])).status_code == 403

    def test_list_returns_only_own_hospital(self, world):
        ca = _case(world["doc_a"], "PAT-A-2").json()["id"]
        cb = _case(world["doc_b"], "PAT-B-2").json()["id"]
        ids = {c["id"] for c in client.get("/cases", headers=bearer(world["doc_a"])).json()}
        assert ca in ids and cb not in ids

    @pytest.mark.parametrize("who", ["admin_a", "super"])
    def test_admins_have_no_patient_level_access(self, world, who):
        cid = _case(world["doc_a"], "PAT-A-3").json()["id"]
        assert client.get(f"/cases/{cid}", headers=bearer(world[who])).status_code == 403
        assert client.get("/cases", headers=bearer(world[who])).status_code == 403
        assert client.post("/cases", json={"patient_ref": "P", "admission_reason": "r"},
                           headers=bearer(world[who])).status_code == 403

    def test_anonymous_denied_and_unknown_case_404(self, world):
        assert client.get("/cases").status_code == 401
        assert client.get("/cases/does-not-exist", headers=bearer(world["doc_a"])).status_code == 404

    def test_update_case(self, world):
        cid = _case(world["doc_a"], "PAT-A-4").json()["id"]
        r = client.patch(f"/cases/{cid}", json={"presenting_symptoms": ["dyspnoea"]},
                         headers=bearer(world["doc_a"]))
        assert r.status_code == 200 and r.json()["presenting_symptoms"] == ["dyspnoea"]

    def test_cross_hospital_attempt_is_audited_without_clinical_content(self, world, caplog):
        cb = _case(world["doc_b"], "PAT-B-5", admission_reason="SECRET-REASON-XYZ").json()["id"]
        with caplog.at_level(logging.INFO, logger="fedheal.audit"):
            client.get(f"/cases/{cb}", headers=bearer(world["doc_a"]))
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "cross_tenant.attempt" in text and cb in text
        assert "SECRET-REASON-XYZ" not in text and "PAT-B-5" not in text


# ---------------- medical history ----------------

class TestHistory:
    def test_create_read_update(self, world):
        cid = _case(world["doc_a"], "PAT-H-1").json()["id"]
        body = {"conditions": ["hypertension"], "allergies": ["penicillin"], "medications": ["amlodipine"],
                "surgeries": [], "family_history": ["father: MI at 60"], "notes": "synthetic"}
        r = client.put(f"/cases/{cid}/history", json=body, headers=bearer(world["doc_a"]))
        assert r.status_code == 200 and r.json()["hospital_id"] == world["ha"]
        body["conditions"] = ["hypertension", "type 2 diabetes"]
        client.put(f"/cases/{cid}/history", json=body, headers=bearer(world["doc_a"]))
        got = client.get(f"/cases/{cid}/history", headers=bearer(world["doc_a"])).json()
        assert got["conditions"] == ["hypertension", "type 2 diabetes"]

    def test_missing_history_is_404_not_an_empty_invention(self, world):
        cid = _case(world["doc_a"], "PAT-H-2").json()["id"]
        assert client.get(f"/cases/{cid}/history", headers=bearer(world["doc_a"])).status_code == 404

    @pytest.mark.parametrize("bad", [{"conditions": "hypertension"}, {"conditions": [""]},
                                     {"allergies": ["x" * 201]}, {"surgeries": ["s"] * 51},
                                     {"notes": "n" * 2001}, {"conditions": [5]}])
    def test_validation(self, world, bad):
        cid = _case(world["doc_a"], "PAT-H-3").json()["id"]
        assert client.put(f"/cases/{cid}/history", json=bad, headers=bearer(world["doc_a"])).status_code == 422

    def test_history_content_never_in_audit_log(self, world, caplog):
        cid = _case(world["doc_a"], "PAT-H-4").json()["id"]
        with caplog.at_level(logging.INFO, logger="fedheal.audit"):
            client.put(f"/cases/{cid}/history", json={"conditions": ["UNIQUE-CONDITION-QQQ"],
                                                      "notes": "UNIQUE-NOTE-QQQ"},
                       headers=bearer(world["doc_a"]))
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "history.write" in text and "QQQ" not in text


# ---------------- vitals linked to a case ----------------

class TestCaseVitals:
    def test_valid_record_is_stored_against_the_case_and_patient_comes_from_the_case(self, world, monkeypatch):
        monkeypatch.setattr(main.httpx, "AsyncClient", _fake_m2("passed"))
        cid = _case(world["doc_a"], "PAT-V-1").json()["id"]
        r = client.post(f"/cases/{cid}/vitals", headers=bearer(world["doc_a"]),
                        json={"record": {**GOOD, "patient_ref": "SOMEONE-ELSE", "hospital_id": world["hb"]}})
        assert r.status_code == 200 and r.json()["validation_status"] == "passed"
        rows = client.get(f"/cases/{cid}/vitals", headers=bearer(world["doc_a"])).json()
        assert len(rows) == 1 and rows[0]["patient_ref"] == "PAT-V-1"
        s = sx.database.SessionLocal()
        try:
            row = s.query(models.VitalsRecord).filter_by(id=rows[0]["id"]).one()
            assert row.hospital_id == world["ha"] and row.case_id == cid
        finally:
            s.close()

    def test_rejected_record_is_not_stored_and_reasons_returned(self, world, monkeypatch):
        monkeypatch.setattr(main.httpx, "AsyncClient", _fake_m2("rejected"))
        cid = _case(world["doc_a"], "PAT-V-2").json()["id"]
        r = client.post(f"/cases/{cid}/vitals", headers=bearer(world["doc_a"]),
                        json={"record": {**GOOD, "systolic_bp": 900}})
        assert r.status_code == 422 and r.json()["detail"]["reasons"]
        assert client.get(f"/cases/{cid}/vitals", headers=bearer(world["doc_a"])).json() == []

    def test_cannot_add_vitals_to_another_hospitals_case(self, world, monkeypatch):
        monkeypatch.setattr(main.httpx, "AsyncClient", _fake_m2("passed"))
        cb = _case(world["doc_b"], "PAT-V-3").json()["id"]
        r = client.post(f"/cases/{cb}/vitals", headers=bearer(world["doc_a"]), json={"record": GOOD})
        assert r.status_code == 403


# ---------------- clinician review ----------------

class TestReview:
    @pytest.mark.parametrize("decision,expected", [("ACCEPTED", "REVIEWED"), ("OVERRIDDEN", "REVIEWED"),
                                                   ("NEEDS_MORE_DATA", "NEEDS_MORE_DATA")])
    def test_decisions(self, world, decision, expected):
        cid = _case(world["doc_a"], f"PAT-R-{decision}").json()["id"]
        r = client.post(f"/cases/{cid}/review", headers=bearer(world["doc_a"]),
                        json={"decision": decision, "clinician_note": "synthetic note"})
        assert r.status_code == 201
        body = r.json()
        assert body["doctor_id"] == world["doc_a_id"] and body["hospital_id"] == world["ha"]
        assert client.get(f"/cases/{cid}", headers=bearer(world["doc_a"])).json()["status"] == expected
        assert len(client.get(f"/cases/{cid}/reviews", headers=bearer(world["doc_a"])).json()) == 1

    def test_invalid_decision_rejected(self, world):
        cid = _case(world["doc_a"], "PAT-R-bad").json()["id"]
        for d in ("APPROVED", "accepted", "", "PRESCRIBE"):
            assert client.post(f"/cases/{cid}/review", json={"decision": d},
                               headers=bearer(world["doc_a"])).status_code == 422

    def test_review_does_not_create_training_labels(self, world):
        cid = _case(world["doc_a"], "PAT-R-nolabel").json()["id"]
        client.post(f"/cases/{cid}/review", json={"decision": "ACCEPTED"}, headers=bearer(world["doc_a"]))
        s = sx.database.SessionLocal()
        try:
            assert s.query(models.VitalsRecord).filter_by(case_id=cid).count() == 0
        finally:
            s.close()

    def test_review_note_never_in_audit_log(self, world, caplog):
        cid = _case(world["doc_a"], "PAT-R-log").json()["id"]
        with caplog.at_level(logging.INFO, logger="fedheal.audit"):
            client.post(f"/cases/{cid}/review", json={"decision": "OVERRIDDEN",
                                                      "clinician_note": "NOTE-QQQ-PHI"},
                        headers=bearer(world["doc_a"]))
        text = "\n".join(r.getMessage() for r in caplog.records)
        assert "clinician.review" in text and "QQQ" not in text

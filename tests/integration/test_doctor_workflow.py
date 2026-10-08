"""
The P0 doctor workflow against the real services (Module 1, 2, 8), no mocks:

  super_admin -> hospital -> hospital_admin -> creates doctor -> doctor logs in
  -> creates case -> vitals (validated by Module 2) -> medical history
  -> AI analysis (Module 8, as the doctor) -> clinician review
  + hospital isolation in both directions, and the safe failure modes.

All data is synthetic. The model behind the analysis is the labelled demo
fallback, so the test asserts it is reported as FALLBACK, never VALIDATED.
Run from the repo root:  pytest tests/integration/test_doctor_workflow.py -v
"""
import uuid

import httpx
import pytest

from test_e2e_flow import ADMIN_PASSWORD, bearer, login, stack  # noqa: F401  (stack is a fixture)

VITALS = {"age_years": 58, "height_cm": 172, "weight_kg": 80, "systolic_bp": 150, "diastolic_bp": 90,
          "heart_rate_bpm": 100, "medication_count": 2, "medication_mg_total": 300}
PW = "doctor-demo-password-1"


def post(url, **kw):
    return httpx.post(url, timeout=30, **kw)


def get(url, **kw):
    return httpx.get(url, timeout=30, **kw)


def make_hospital_with_doctor(m1, super_token):
    h = post(f"{m1.url}/hospitals", json={"name": f"WF {uuid.uuid4().hex[:8]}"}, headers=bearer(super_token))
    assert h.status_code == 200, h.text
    hid = h.json()["id"]
    admin_email = f"hadmin-{uuid.uuid4().hex[:8]}@wf.fedheal.local"
    a = post(f"{m1.url}/admin/users", json={"email": admin_email, "password": PW, "role": "hospital_admin",
                                           "hospital_id": hid}, headers=bearer(super_token))
    assert a.status_code == 200, a.text
    admin_tok = login(m1, admin_email, PW)
    doc_email = f"doc-{uuid.uuid4().hex[:8]}@wf.fedheal.local"
    d = post(f"{m1.url}/hospital/doctors", json={"full_name": "Dr Demo", "email": doc_email, "password": PW},
             headers=bearer(admin_tok))
    assert d.status_code == 201, d.text
    return {"hid": hid, "admin": admin_tok, "doctor_id": d.json()["id"], "doctor": login(m1, doc_email, PW)}


@pytest.fixture(scope="module")
def wf(stack):  # noqa: F811
    m1 = stack["m1"]
    sup = login(m1, "admin@e2e.fedheal.local", ADMIN_PASSWORD)
    return {"m1": m1, "m8": stack["m8"], "m8_nomodel": stack["m8_nomodel"], "a": make_hospital_with_doctor(m1, sup),
            "b": make_hospital_with_doctor(m1, sup)}


def new_case(wf, who="a", ref=None):
    r = post(f"{wf['m1'].url}/cases", headers=bearer(wf[who]["doctor"]),
             json={"patient_ref": ref or f"PAT-DEMO-{uuid.uuid4().hex[:6]}", "admission_reason": "Chest discomfort (synthetic)",
                   "current_condition": "heart_disease", "presenting_symptoms": ["chest pain"]})
    assert r.status_code == 201, r.text
    return r.json()


def test_full_workflow_end_to_end(wf):
    m1, m8, tok = wf["m1"], wf["m8"], wf["a"]["doctor"]
    case = new_case(wf)
    assert case["hospital_id"] == wf["a"]["hid"]

    v = post(f"{m1.url}/cases/{case['id']}/vitals", headers=bearer(tok), json={"record": VITALS})
    assert v.status_code == 200 and v.json()["validation_status"] in ("passed", "flagged"), v.text
    assert v.json()["validation_status"] == "passed"

    h = client_put(f"{m1.url}/cases/{case['id']}/history", tok,
                   {"conditions": ["hypertension"], "allergies": ["penicillin"], "medications": ["amlodipine"]})
    assert h.status_code == 200, h.text

    r = post(f"{m8.url}/cases/{case['id']}/analyze", headers=bearer(tok))
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["available_modalities"] == ["vitals", "medical_history"]
    assert "scan" in rep["missing_modalities"]
    assert rep["model"]["status"] == "FALLBACK" and rep["stub_or_fallback"] is True
    assert rep["clinician_review_required"] is True and rep["safety"]["banner"].startswith("AI Clinical Decision Support")
    assert rep["explanation"]["status"] in ("available", "unavailable")

    rv = post(f"{m1.url}/cases/{case['id']}/review", headers=bearer(tok),
              json={"decision": "OVERRIDDEN", "clinician_note": "synthetic override"})
    assert rv.status_code == 201 and rv.json()["doctor_id"] == wf["a"]["doctor_id"]
    assert get(f"{m1.url}/cases/{case['id']}", headers=bearer(tok)).json()["status"] == "REVIEWED"


def client_put(url, token, body):
    return httpx.put(url, json=body, headers=bearer(token), timeout=30)


def test_hospital_isolation_both_directions_across_real_services(wf):
    m1, m8 = wf["m1"], wf["m8"]
    ca, cb = new_case(wf, "a"), new_case(wf, "b")
    ta, tb = wf["a"]["doctor"], wf["b"]["doctor"]
    for tok, other in ((ta, cb), (tb, ca)):
        assert get(f"{m1.url}/cases/{other['id']}", headers=bearer(tok)).status_code == 403
        assert get(f"{m1.url}/cases/{other['id']}/history", headers=bearer(tok)).status_code == 403
        assert post(f"{m1.url}/cases/{other['id']}/review", headers=bearer(tok),
                    json={"decision": "ACCEPTED"}).status_code == 403
        assert post(f"{m1.url}/cases/{other['id']}/vitals", headers=bearer(tok),
                    json={"record": VITALS}).status_code == 403
        assert post(f"{m8.url}/cases/{other['id']}/analyze", headers=bearer(tok)).status_code == 403
    assert {c["id"] for c in get(f"{m1.url}/cases", headers=bearer(ta)).json()} >= {ca["id"]}
    assert cb["id"] not in {c["id"] for c in get(f"{m1.url}/cases", headers=bearer(ta)).json()}


def test_hospital_admin_cannot_create_doctor_elsewhere_or_read_patients(wf):
    m1 = wf["m1"]
    r = post(f"{m1.url}/hospital/doctors", headers=bearer(wf["a"]["admin"]),
             json={"full_name": "X", "email": f"x-{uuid.uuid4().hex[:6]}@wf.local", "password": PW,
                   "hospital_id": wf["b"]["hid"]})
    assert r.status_code == 403
    case = new_case(wf, "a")
    assert get(f"{m1.url}/cases/{case['id']}", headers=bearer(wf["a"]["admin"])).status_code == 403


def test_disabled_doctor_is_locked_out(wf):
    m1 = wf["m1"]
    email = f"temp-{uuid.uuid4().hex[:6]}@wf.fedheal.local"
    d = post(f"{m1.url}/hospital/doctors", headers=bearer(wf["a"]["admin"]),
             json={"full_name": "Temp", "email": email, "password": PW}).json()
    tok = login(m1, email, PW)
    assert get(f"{m1.url}/cases", headers=bearer(tok)).status_code == 200
    assert httpx.patch(f"{m1.url}/hospital/doctors/{d['id']}", json={"is_active": False},
                       headers=bearer(wf["a"]["admin"]), timeout=30).status_code == 200
    assert get(f"{m1.url}/cases", headers=bearer(tok)).status_code == 401


def test_analysis_refuses_to_guess_when_data_is_missing(wf):
    m1, m8, tok = wf["m1"], wf["m8"], wf["a"]["doctor"]
    case = new_case(wf)                                      # no vitals at all
    r = post(f"{m8.url}/cases/{case['id']}/analyze", headers=bearer(tok))
    assert r.status_code == 422 and r.json()["detail"]["status"] == "INSUFFICIENT_DATA"
    assert "prediction" not in r.json()["detail"] and "confidence" not in r.json()["detail"]
    partial = {k: v for k, v in VITALS.items() if k != "diastolic_bp"}     # a field the model needs
    post(f"{m1.url}/cases/{case['id']}/vitals", headers=bearer(tok), json={"record": partial})
    r = post(f"{m8.url}/cases/{case['id']}/analyze", headers=bearer(tok))
    assert r.status_code in (422,) and r.json()["detail"]["status"] == "INSUFFICIENT_DATA"


def test_invalid_vitals_are_rejected_and_not_stored(wf):
    m1, tok = wf["m1"], wf["a"]["doctor"]
    case = new_case(wf)
    r = post(f"{m1.url}/cases/{case['id']}/vitals", headers=bearer(tok),
             json={"record": {**VITALS, "systolic_bp": 900}})
    assert r.status_code == 422
    assert get(f"{m1.url}/cases/{case['id']}/vitals", headers=bearer(tok)).json() == []


def test_model_unavailable_is_explicit_when_no_model_is_loaded(wf):
    m1, tok = wf["m1"], wf["a"]["doctor"]
    case = new_case(wf)
    post(f"{m1.url}/cases/{case['id']}/vitals", headers=bearer(tok), json={"record": VITALS})
    r = post(f"{wf['m8_nomodel'].url}/cases/{case['id']}/analyze", headers=bearer(tok))
    assert r.status_code == 503 and r.json()["detail"]["status"] == "MODEL_UNAVAILABLE"

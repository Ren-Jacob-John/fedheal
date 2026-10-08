"""POST /cases/{case_id}/analyze — what is returned for a complete case and the
explicit answers for every way it can't run. Module 1 is replaced by a stub
`fetch_case_bundle`; the real chain is exercised in tests/integration."""
import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt

import auth
import main

client = TestClient(main.app)
VITALS = {"id": "v1", "patient_ref": "PAT-DEMO-001", "age_years": 58, "height_cm": 172, "weight_kg": 80,
          "systolic_bp": 150, "diastolic_bp": 90, "heart_rate_bpm": 100, "medication_count": 2,
          "medication_mg_total": 300, "validation_status": "passed"}
HISTORY = {"case_id": "c1", "conditions": ["hypertension"], "allergies": [], "notes": "HX-NOTE-QQQ"}
CASE = {"id": "c1", "hospital_id": "h1", "patient_ref": "PAT-DEMO-001", "current_condition": "heart_disease",
        "admission_reason": "synthetic", "presenting_symptoms": []}


def headers():
    tok = jwt.encode({"sub": "u1", "role": "clinician", "hospital_id": "h1", "exp": int(time.time()) + 600},
                     auth.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture()
def bundle(monkeypatch):
    holder = {"case": dict(CASE), "history": dict(HISTORY), "vitals": [dict(VITALS)]}

    async def fake(case_id, token):
        return holder
    monkeypatch.setattr(main, "fetch_case_bundle", fake)
    return holder


def analyze(case_id="c1"):
    return client.post(f"/cases/{case_id}/analyze", headers=headers())


def test_complete_case_reports_modalities_model_status_and_review_flag(bundle):
    r = analyze()
    assert r.status_code == 200
    b = r.json()
    assert b["available_modalities"] == ["vitals", "medical_history"]
    assert {"scan", "labs"} <= set(b["missing_modalities"])
    assert b["clinician_review_required"] is True
    assert b["model"]["status"] == "FALLBACK" and b["stub_or_fallback"] is True   # demo-fit model, never VALIDATED
    assert b["model"]["name"] and b["model"]["version"]
    assert b["safety"]["banner"].startswith("AI Clinical Decision Support")
    assert "Imaging evidence" not in b["basis_statement"] and "Scan evidence was not available" in b["basis_statement"]
    assert b["uncertainty"]["calibrated"] is False


def test_history_is_context_not_a_model_input_and_content_is_not_echoed_as_evidence(bundle):
    b = analyze().json()
    hist = [e for e in b["evidence"] if e["source"] == "medical_history"][0]
    assert hist["used_by_model"] is False
    assert all(e["used_by_model"] for e in b["evidence"] if e["source"] == "vitals")
    assert "HX-NOTE-QQQ" not in str(b)


def test_missing_history_is_reported_missing(bundle):
    bundle["history"] = None
    b = analyze().json()
    assert b["available_modalities"] == ["vitals"] and "medical_history" in b["missing_modalities"]


def test_no_vitals_is_insufficient_data_not_a_prediction(bundle):
    bundle["vitals"] = []
    r = analyze()
    assert r.status_code == 422 and r.json()["detail"]["status"] == "INSUFFICIENT_DATA"
    assert "vitals" in r.json()["detail"]["missing_modalities"]
    assert "prediction" not in r.json()["detail"] and "confidence" not in r.json()["detail"]


def test_flagged_only_vitals_are_not_analysed(bundle):
    bundle["vitals"] = [dict(VITALS, validation_status="flagged")]
    r = analyze()
    assert r.status_code == 422 and r.json()["detail"]["status"] == "INSUFFICIENT_DATA"


def test_vitals_with_missing_inputs_are_not_filled_in(bundle):
    bundle["vitals"] = [dict(VITALS, diastolic_bp=None)]
    r = analyze()
    d = r.json()["detail"]
    assert r.status_code == 422 and d["status"] == "INSUFFICIENT_DATA" and d["missing_features"] == ["diastolic_bp"]


def test_condition_needing_scans_is_model_unavailable(bundle):
    bundle["case"]["current_condition"] = "pneumonia"
    r = analyze()
    assert r.status_code == 422 and r.json()["detail"]["status"] == "MODEL_UNAVAILABLE"


def test_unknown_condition_is_explicit(bundle):
    bundle["case"]["current_condition"] = "not-a-condition"
    assert analyze().status_code == 404


def test_model_not_loaded_is_503_model_unavailable(bundle, monkeypatch):
    monkeypatch.setattr(main.router.specialists["vitals"], "is_available", lambda: False)
    r = analyze()
    assert r.status_code == 503 and r.json()["detail"]["status"] == "MODEL_UNAVAILABLE"


def test_unauthenticated_denied(bundle):
    assert client.post("/cases/c1/analyze").status_code == 401


def test_other_hospitals_case_is_forbidden_end_to_end(monkeypatch):
    async def forbidden(case_id, token):
        raise main._error(403, "forbidden", "Not permitted for this case")
    monkeypatch.setattr(main, "fetch_case_bundle", forbidden)
    assert analyze().status_code == 403


def test_no_treatment_or_diagnosis_fields(bundle):
    b = analyze().json()
    text = str(b).lower()
    for banned in ("prescri", "dosage", "treatment plan", "definitive diagnosis"):
        assert banned not in text.replace("not a diagnosis", "")


def test_uploaded_scan_is_reported_stored_but_never_analysed(bundle):
    bundle["scans"] = [{"scan_id": "s1", "scan_type": "chest_xray", "status": "UPLOADED"}]
    b = analyze().json()
    assert b["uploaded_unanalysed_modalities"]["scan"]["analysis"].startswith("UNAVAILABLE")
    assert "scan" in b["missing_modalities"]                      # no analysable scan evidence exists
    assert "no validated imaging model" in b["basis_statement"] and "1 scan(s) are stored" in b["basis_statement"]
    assert "Scan evidence was not available" not in b["basis_statement"]
    assert not any(f.get("source") in ("imaging", "scan") for f in b["findings"])


def test_scan_only_condition_gives_an_explicit_unavailable_response_not_findings(bundle):
    bundle["case"]["current_condition"] = "pneumonia"
    bundle["vitals"] = []
    bundle["scans"] = [{"scan_id": "s1", "scan_type": "chest_xray", "status": "UPLOADED"}]
    r = analyze()
    d = r.json()["detail"]
    assert r.status_code == 422 and d["status"] == "MODEL_UNAVAILABLE"
    assert d["uploaded_unanalysed_modalities"]["scan"]["status"] == "UPLOADED" and "findings" not in d


def test_condition_is_never_guessed(bundle):
    bundle["case"]["current_condition"] = None
    r = analyze()
    assert r.status_code == 422 and r.json()["detail"]["status"] == "CONDITION_NOT_SET"
    assert "prediction" not in r.json()["detail"] and "findings" not in r.json()["detail"]

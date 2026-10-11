"""Safety tests for versioned clinician-review considerations."""
import re
import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt

import auth
import considerations
import main
import promoted_model


client = TestClient(main.app)
CASE = {
    "id": "c1",
    "hospital_id": "h1",
    "patient_ref": "PAT-DEMO-001",
    "current_condition": "heart_disease",
    "admission_reason": "synthetic",
    "presenting_symptoms": [],
}
VITALS = {
    "id": "v1",
    "patient_ref": "PAT-DEMO-001",
    "age_years": 58,
    "height_cm": 172,
    "weight_kg": 80,
    "systolic_bp": 150,
    "diastolic_bp": 90,
    "heart_rate_bpm": 100,
    "medication_count": 2,
    "medication_mg_total": 300,
    "validation_status": "passed",
}


def _headers():
    token = jwt.encode(
        {"sub": "u1", "role": "clinician", "hospital_id": "h1", "exp": int(time.time()) + 600},
        auth.SECRET_KEY,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def configured_analysis(monkeypatch):
    async def fake_bundle(case_id, token):
        return {"case": dict(CASE), "history": None, "vitals": [dict(VITALS)], "scans": []}

    monkeypatch.setattr(main, "fetch_case_bundle", fake_bundle)
    async def fake_persist(case_id, token, packet):
        return "analysis-test-id"
    monkeypatch.setattr(main, "persist_case_analysis", fake_persist)
    monkeypatch.setattr(promoted_model, "fetch_promoted", lambda condition: None)
    monkeypatch.setenv("FEDHEAL_ALLOW_DEMO_MODEL", "true")
    promoted_model.clear_cache()
    yield
    promoted_model.clear_cache()


def test_considerations_require_an_explicit_rule_match():
    result = considerations.considerations_for("condition-without-a-rule")
    assert result["status"] == "no_match"
    assert result["message"] == "no suggestion available"
    assert result["items"] == []


def test_every_rule_has_version_provenance_and_review_status():
    for rule in considerations.RULES:
        assert rule["version"]
        assert rule["source"]
        assert rule["provenance"]
        assert rule["validation_status"] == "unvalidated - for clinician review"


def test_analysis_packet_requires_review_and_has_no_dosing_text(configured_analysis):
    response = client.post("/cases/c1/analyze", headers=_headers())
    assert response.status_code == 200, response.text
    packet = response.json()
    assert packet["requires_clinician_review"] is True
    assert "reasoning" in packet
    assert "suggested_considerations" in packet
    assert all(
        rule["validation_status"] == "unvalidated - for clinician review"
        for rule in packet["suggested_considerations"]["items"]
    )

    text = str(packet).lower()
    assert not re.search(r"\b(?:take|administer|prescribe)\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml)\b", text)
    assert not re.search(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|ml)\s+(?:daily|twice|three times|every)\b", text)
    assert "diagnosis confirmed" not in text

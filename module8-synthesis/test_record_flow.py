"""
Module 8 record-based flow: what is returned for a valid record, and the
explicit, structured answers for every way it can not run. Module 1 is
replaced by a stub `fetch_record`; the real Module 1 -> 2 -> 8 chain is
covered by tests/integration/test_e2e_flow.py.
"""
import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt

import auth
import feature_mapper
import main

client = TestClient(main.app)
VITALS_FIELDS = ["age_years", "systolic_bp", "diastolic_bp", "heart_rate_bpm",
                 "weight_kg", "height_cm", "medication_count", "medication_mg_total"]
RECORD = {"id": "rec-1", "patient_ref": "P-1", "age_years": 58, "height_cm": 172, "weight_kg": 80,
          "systolic_bp": 150, "diastolic_bp": 90, "heart_rate_bpm": 100, "medication_count": 2,
          "medication_mg_total": 300, "label": 1, "label_source": "hospital", "validation_status": "passed"}


def headers():
    tok = jwt.encode({"sub": "u1", "role": "clinician", "hospital_id": "h1", "exp": int(time.time()) + 600},
                     auth.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture()
def record(monkeypatch):
    holder = {"rec": dict(RECORD)}

    async def fake(record_id, token):
        return dict(holder["rec"], id=record_id)
    monkeypatch.setattr(main, "fetch_record", fake)
    return holder["rec"], holder


def post(body=None, **kw):
    return client.post("/synthesize/record", json=body or {"record_id": "rec-1"}, headers=headers(), **kw)


# ---- mapping contract ----------------------------------------------------

def test_mapping_matches_specialist_declared_features():
    feature_mapper.verify_mapping(main.router.specialists["vitals"].feature_names)
    assert [r.model_feature for r in feature_mapper.VITALS_MAPPING] == VITALS_FIELDS


def test_mapper_reports_missing_and_never_fills():
    m = feature_mapper.map_record({**RECORD, "diastolic_bp": None, "heart_rate_bpm": None})
    assert m.missing == ["diastolic_bp", "heart_rate_bpm"] and not m.complete
    assert m.features[2] is None and m.features[3] is None      # not 0, not a mean


def test_mapper_never_uses_label_or_identifiers_as_input():
    m = feature_mapper.map_record(RECORD)
    assert len(m.features) == 8
    assert all(i["source_field"] not in feature_mapper.NON_INPUT_FIELDS for i in m.inputs)


def test_mapper_drift_is_detected():
    with pytest.raises(feature_mapper.MappingDriftError):
        feature_mapper.verify_mapping(["age", "resting_bp", "cholesterol", "max_heart_rate",
                                       "bmi", "glucose", "num_medications", "prior_admissions"])


# ---- valid record --------------------------------------------------------

def test_valid_record_returns_full_structured_response(record):
    r = post()
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "ok" and d["condition"] == "heart_disease"
    assert d["record"] == {"record_id": "rec-1", "patient_ref": "P-1", "validation_status": "passed"}
    assert d["specialist"]["specialist_id"] == "vitals"
    assert d["prediction"]["label"] in ("high_risk", "low_risk")
    assert "synthesis" in d and d["synthesis"]["requires_clinician_review"] is True


def test_specialist_metadata_is_present_and_honest(record):
    spec = post().json()["specialist"]
    for key in ("model_name", "model_version", "is_stub", "is_fallback", "training_status", "feature_names"):
        assert key in spec
    assert spec["is_stub"] is False
    assert spec["is_fallback"] is True and spec["training_status"] == "demo_fit"   # never "federated"
    model = post().json()["model"]
    assert model["federated"] is False and model["hospital_trained"] is False


def test_fallback_is_clearly_marked_in_warnings(record):
    codes = {w["code"] for w in post().json()["warnings"]}
    assert {"fallback_model", "demo_training_data"} <= codes


def test_explanation_fields_are_exactly_the_model_inputs(record):
    d = post().json()
    exp = d["explanation"]
    assert exp["status"] == "available" and exp["method"] == "shap"
    assert exp["feature_names"] == VITALS_FIELDS
    assert [c["feature"] for c in exp["contributions"]] == VITALS_FIELDS
    values = {i["feature"]: i["value"] for i in d["inputs"]}
    assert {c["feature"]: c["value"] for c in exp["contributions"]} == values
    assert values["age_years"] == 58.0 and values["systolic_bp"] == 150.0     # record values, unchanged


def test_shap_unavailable_yields_explicit_status_not_fabrication(record, monkeypatch):
    import explainers.shap_explainer as se
    monkeypatch.setattr(se, "SHAP_AVAILABLE", False)
    exp = post().json()["explanation"]
    assert exp["status"] == "unavailable" and exp["contributions"] == []
    assert "not available" in exp["reason"]


def test_knowledge_graph_text_does_not_claim_features_drove_the_result(record):
    kg = post().json()["synthesis"]["findings"][0]["explanation_details"]["knowledge_graph"]
    assert "glucose" not in kg["reason"].lower() and "medication load" not in kg["reason"].lower()


# ---- rejections ----------------------------------------------------------

def test_missing_model_feature_is_reported_by_name(record):
    rec, _ = record
    rec["diastolic_bp"] = None
    rec["heart_rate_bpm"] = None
    r = post()
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["status"] == "incomplete_data" and d["missing_features"] == ["diastolic_bp", "heart_rate_bpm"]
    assert "prediction" not in r.text


def test_flagged_record_is_not_synthesized(record):
    rec, _ = record
    rec["validation_status"] = "flagged"
    r = post()
    assert r.status_code == 409 and r.json()["detail"]["status"] == "record_not_validated"


def test_unknown_condition_is_explicit(record):
    r = post({"record_id": "rec-1", "condition": "not_a_disease"})
    assert r.status_code == 404
    d = r.json()["detail"]
    assert d["status"] == "unknown_condition" and "heart_disease" in d["known_conditions"]


def test_condition_needing_other_modalities_is_refused_and_shows_stub_status(record):
    r = post({"record_id": "rec-1", "condition": "pneumonia"})
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["status"] == "unsupported_input"
    chest = d["specialists"][0]
    assert chest["specialist_id"] == "chest_xray" and chest["is_stub"] is True and chest["is_fallback"] is True


def test_alias_selects_the_same_specialist(record):
    d = post({"record_id": "rec-1", "condition": "cardiac risk"}).json()
    assert d["condition"] == "heart_disease" and d["specialist"]["specialist_id"] == "vitals"


def test_unavailable_specialist_is_503_with_status_not_a_silent_fallback(record):
    spec = main.router.specialists["vitals"]
    spec._is_fitted = False
    try:
        r = post()
    finally:
        spec._is_fitted = True
    assert r.status_code == 503
    d = r.json()["detail"]
    assert d["status"] == "specialist_unavailable" and d["specialist"]["available"] is False


def test_upstream_403_and_404_are_passed_through(monkeypatch):
    for code, status in ((403, "forbidden"), (404, "record_not_found")):
        async def fake(record_id, token, code=code, status=status):
            raise main._error(code, status, "x")
        monkeypatch.setattr(main, "fetch_record", fake)
        r = post()
        assert r.status_code == code and r.json()["detail"]["status"] == status


def test_legacy_manual_feature_endpoint_is_gone():
    r = client.post("/synthesize/heart_disease", json={"features": [1.0] * 8}, headers=headers())
    assert r.status_code == 410 and r.json()["detail"]["status"] == "endpoint_removed"


# ---- status endpoint -----------------------------------------------------

def test_models_status_reports_stub_and_fallback_flags():
    d = client.get("/models/status", params={"condition": "heart_disease"}, headers=headers()).json()
    assert d["record_flow_supported"] is True and d["vitals_model"]["federated"] is False
    assert d["specialists"][0]["training_status"] == "demo_fit"
    pn = client.get("/models/status", params={"condition": "pneumonia"}, headers=headers()).json()
    assert pn["record_flow_supported"] is False and pn["specialists"][0]["is_stub"] is True
    assert client.get("/models/status", params={"condition": "zzz"}, headers=headers()).status_code == 404
    assert client.get("/models/status").status_code == 401


def test_demo_model_requires_an_explicit_flag_in_every_environment(monkeypatch):
    import model_provider
    monkeypatch.setenv("FEDHEAL_ENV", "production")
    monkeypatch.delenv("FEDHEAL_ALLOW_DEMO_MODEL", raising=False)
    assert model_provider.demo_model_allowed() is False
    monkeypatch.setenv("FEDHEAL_ENV", "development")
    assert model_provider.demo_model_allowed() is False      # no implicit development default any more
    monkeypatch.setenv("FEDHEAL_ALLOW_DEMO_MODEL", "true")
    assert model_provider.demo_model_allowed() is True

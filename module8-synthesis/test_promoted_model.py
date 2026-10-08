"""Inference must use the PROMOTED federated model when the registry has one, never an accidental demo model.
The registry is replaced by a stub here; the real Module 7 <-> Module 8 path is in tests/integration/test_federation_flow.py.
Weights/metrics below are SYNTHETIC test inputs."""
import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt

import auth
import main
import model_provider
import promoted_model as pm

client = TestClient(main.app)
VITALS = {"id": "v1", "patient_ref": "PAT-DEMO-001", "age_years": 58, "height_cm": 172, "weight_kg": 80,
          "systolic_bp": 150, "diastolic_bp": 90, "heart_rate_bpm": 100, "medication_count": 2,
          "medication_mg_total": 300, "validation_status": "passed"}
CASE = {"id": "c1", "hospital_id": "h1", "patient_ref": "PAT-DEMO-001", "current_condition": "heart_disease",
        "admission_reason": "synthetic", "presenting_symptoms": []}
NAMES = ["age_years", "systolic_bp", "diastolic_bp", "heart_rate_bpm", "weight_kg", "height_cm",
         "medication_count", "medication_mg_total"]
COEF = [0.5, 0.4, 0.1, 0.3, 0.0, 0.0, 0.0, 0.0]


def body(**over):
    coef, icpt = COEF, -0.1
    b = {"id": "reg-1", "model_name": "vitals-fedavg-logreg", "version": "v7", "condition": "heart_disease",
         "training_round": 8, "n_participating_hospitals": 2, "artifact_hash": pm._canonical_hash(coef, icpt),
         "metrics": {"accuracy": 0.7, "n_eval": 100, "majority_class_floor": 0.55}, "approved_at": "2026-10-07T00:00:00",
         "parameters": {"coef": [coef], "intercept": [icpt]},
         "input_spec": {"feature_names": NAMES, "center": [50, 120, 80, 75, 75, 170, 2, 150],
                        "scale": [20, 20, 10, 12, 18, 12, 2, 120]}}
    b.update(over)
    return b


def headers():
    t = jwt.encode({"sub": "u1", "role": "clinician", "hospital_id": "h1", "exp": int(time.time()) + 600},
                   auth.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(autouse=True)
def case_bundle(monkeypatch):
    async def fake(case_id, token):
        return {"case": dict(CASE), "history": {"conditions": []}, "vitals": [dict(VITALS)]}
    monkeypatch.setattr(main, "fetch_case_bundle", fake)
    pm.clear_cache()
    yield
    pm.clear_cache()


def registry(monkeypatch, result):
    def fetch(condition, **kw):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(pm, "fetch_promoted", fetch)


def analyze():
    return client.post("/cases/c1/analyze", headers=headers())


def test_promoted_model_is_used_and_labelled_with_its_provenance(monkeypatch):
    registry(monkeypatch, pm._parse(body()))
    r = analyze()
    assert r.status_code == 200, r.text
    b = r.json()
    m = b["model"]
    assert m["version"] == "v7" and m["status"] == "DEPLOYED" and m["federated"] is True
    assert m["provenance"]["artifact_hash"] == body()["artifact_hash"] and m["provenance"]["n_participating_hospitals"] == 2
    assert b["stub_or_fallback"] is False and b["clinician_review_required"] is True and b["non_clinical"] is True
    assert "not been clinically validated" in m["note"]
    assert b["explanation"]["method"] == "linear_contributions" and len(b["explanation"]["contributions"]) == 8
    assert "DEMO" not in str(b["model"].get("label", ""))


def test_promoted_model_beats_an_available_demo_model(monkeypatch):
    """Demo flag is ON in this suite; the promoted model must still win."""
    assert model_provider.demo_model_allowed() is True
    registry(monkeypatch, pm._parse(body(version="v3")))
    assert analyze().json()["model"]["version"] == "v3"


def test_prediction_matches_the_registry_weights_exactly(monkeypatch):
    registry(monkeypatch, pm._parse(body()))
    b = analyze().json()
    x = [(VITALS[n] - c) / s for n, c, s in zip(NAMES, [50, 120, 80, 75, 75, 170, 2, 150], [20, 20, 10, 12, 18, 12, 2, 120])]
    z = sum(w * v for w, v in zip(COEF, x)) - 0.1
    assert b["explanation"]["base_value"] == pytest.approx(-0.1)
    assert sum(c["contribution"] for c in b["explanation"]["contributions"]) + b["explanation"]["base_value"] == pytest.approx(z)


def test_demo_fallback_is_labelled_non_clinical_when_no_model_is_promoted(monkeypatch):
    registry(monkeypatch, None)
    b = analyze().json()
    assert b["model"]["status"] == "FALLBACK" and b["model"]["federated"] is False
    assert "NON-CLINICAL DEMO MODEL" in b["model"]["label"] and b["non_clinical"] is True and b["stub_or_fallback"] is True


def test_no_promoted_model_and_demo_disabled_is_model_unavailable(monkeypatch):
    registry(monkeypatch, None)
    monkeypatch.setenv("FEDHEAL_ALLOW_DEMO_MODEL", "false")
    monkeypatch.setattr(main.router.specialists["vitals"], "is_available", lambda: False)
    r = analyze()
    assert r.status_code == 503 and r.json()["detail"]["status"] == "MODEL_UNAVAILABLE"


def test_registry_down_never_silently_serves_the_demo_model(monkeypatch):
    registry(monkeypatch, pm.RegistryUnavailable("Module 7 (model registry) could not be reached"))
    monkeypatch.setenv("FEDHEAL_ALLOW_DEMO_MODEL", "false")
    r = analyze()
    assert r.status_code == 503 and r.json()["detail"]["status"] == "MODEL_UNAVAILABLE"
    assert "registry" in r.json()["detail"]
    # explicitly enabled demo + registry down: allowed, but the response says so
    monkeypatch.setenv("FEDHEAL_ALLOW_DEMO_MODEL", "true")
    b = analyze().json()
    assert b["model"]["status"] == "FALLBACK" and any(w["code"] == "registry_unreachable" for w in b["warnings"])


def test_tampered_weights_are_refused():
    bad = body()
    bad["parameters"]["coef"][0][0] = 9.9
    with pytest.raises(pm.PromotedModelIntegrityError):
        pm._parse(bad)


def test_integrity_failure_blocks_inference(monkeypatch):
    registry(monkeypatch, pm.PromotedModelIntegrityError("promoted weights do not match their artifact_hash"))
    r = analyze()
    assert r.status_code == 503 and r.json()["detail"]["status"] == "MODEL_UNAVAILABLE"


def test_incomplete_vitals_still_give_explicit_missing_inputs_with_a_promoted_model(monkeypatch):
    registry(monkeypatch, pm._parse(body()))

    async def fake(case_id, token):
        return {"case": dict(CASE), "history": None, "vitals": [dict(VITALS, diastolic_bp=None)]}
    monkeypatch.setattr(main, "fetch_case_bundle", fake)
    r = analyze()
    assert r.status_code == 422 and r.json()["detail"]["missing_features"] == ["diastolic_bp"]

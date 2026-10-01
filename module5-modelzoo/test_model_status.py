"""
Module 5: every specialist reports whether it is real, a stub or a fallback,
and vitals predictions carry that provenance.

Run:  pytest test_model_status.py -v
"""
import numpy as np
import pytest

from models.stub import StubSpecialistModel
from models.tabular_vitals import FEATURE_NAMES, XGBoostVitalsModel
from registry import build_registry, registry_status

FIELDS = ["age_years", "systolic_bp", "diastolic_bp", "heart_rate_bpm",
          "weight_kg", "height_cm", "medication_count", "medication_mg_total"]


def test_vitals_feature_contract_is_module1_schema():
    assert FEATURE_NAMES == FIELDS and XGBoostVitalsModel().feature_names == FIELDS


def test_unfitted_vitals_is_untrained_and_unavailable():
    m = XGBoostVitalsModel()
    card = m.describe()
    assert card["training_status"] == "untrained" and card["available"] is False and card["is_stub"] is False
    with pytest.raises(RuntimeError, match="before fit"):
        m.predict({"features": [1.0] * 8})


def test_fit_records_provenance_and_defaults_to_demo():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(60, 8))
    m = XGBoostVitalsModel().fit(X, (X[:, 0] > 0).astype(int))
    assert m.training_status == "demo_fit"          # the less flattering default
    m.fit(X, (X[:, 0] > 0).astype(int), training_status="federated", model_version="round-7", is_fallback=False)
    res = m.predict({"features": X[0].tolist()})
    assert (res.training_status, res.model_version, res.is_fallback, res.is_stub) == ("federated", "round-7", False, False)


def test_predict_refuses_missing_or_wrong_width_input():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(60, 8))
    m = XGBoostVitalsModel().fit(X, (X[:, 0] > 0).astype(int))
    with pytest.raises(ValueError):
        m.predict({"features": [1.0, float("nan")] + [1.0] * 6})
    with pytest.raises(ValueError):
        m.predict({"features": [1.0] * 5})
    with pytest.raises(ValueError):
        m.fit(np.zeros((5, 3)), np.array([0, 1, 0, 1, 0]))


def test_stub_is_never_presented_as_real():
    s = StubSpecialistModel("cxr", "chest_xray", "classification", ["normal", "pneumonia"], "densenet")
    assert (s.is_stub, s.is_fallback, s.training_status) == (True, True, "none")
    r = s.predict({})
    assert r.is_stub and r.is_fallback and r.training_status == "none"


def test_registry_status_exposes_stub_fallback_and_training_status():
    rows = registry_status(build_registry())
    for row in rows:
        assert {"is_stub", "is_fallback", "training_status", "model_version", "available"} <= set(row)
        if row["model_name"].startswith("stub-"):
            assert row["is_stub"] is True and row["real"] is False
    assert any(r["modality"] == "vitals" and r["is_stub"] is False for r in rows)

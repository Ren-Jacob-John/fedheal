"""
Module 6 condition routing: specialist selection, required-input validation,
explicit unknown/unavailable/incomplete outcomes, status metadata, and the
SHAP / knowledge-graph honesty rules.

Run:  pytest test_routing.py -v
"""
import numpy as np
import pytest

from condition_router import (
    ConditionRouter, IncompleteDataError, SpecialistUnavailableError, UnknownConditionError,
)
import explainers.shap_explainer as shap_mod

FIELDS = ["age_years", "systolic_bp", "diastolic_bp", "heart_rate_bpm",
          "weight_kg", "height_cm", "medication_count", "medication_mg_total"]


@pytest.fixture(scope="module")
def router():
    r = ConditionRouter()
    rng = np.random.default_rng(0)
    X = rng.normal(size=(80, 8))
    r.specialists["vitals"].fit(X, (X[:, 0] > 0).astype(int), training_status="demo_fit", is_fallback=True)
    return r


def features():
    return [50.0, 130.0, 80.0, 70.0, 70.0, 170.0, 1.0, 100.0]


def test_condition_selects_the_right_specialist(router):
    assert [c["specialist_id"] for c in router.status_for_condition("heart_disease")] == ["vitals"]
    assert [c["specialist_id"] for c in router.status_for_condition("Cardiac Risk")] == ["vitals"]     # alias
    assert [c["specialist_id"] for c in router.status_for_condition("pneumonia")] == ["chest_xray"]
    assert [c["specialist_id"] for c in router.status_for_condition("tb")] == ["chest_xray"]


def test_unknown_condition_is_an_explicit_error(router):
    with pytest.raises(UnknownConditionError, match="isn't registered"):
        router.route("made_up_disease", {})
    with pytest.raises(UnknownConditionError):
        router.status_for_condition("made_up_disease")


def test_missing_features_raise_incomplete_data_naming_them(router):
    f = features()
    f[2] = None
    f[3] = float("nan")
    with pytest.raises(IncompleteDataError) as e:
        router.route("heart_disease", {"vitals": {"features": f}})
    assert e.value.missing_features == ["diastolic_bp", "heart_rate_bpm"] and e.value.specialist_id == "vitals"


def test_wrong_length_is_incomplete_not_truncated(router):
    with pytest.raises(IncompleteDataError):
        router.route("heart_disease", {"vitals": {"features": [1.0, 2.0, 3.0]}})


def test_unfitted_specialist_is_unavailable_not_guessed():
    r = ConditionRouter()          # fresh: vitals not fitted
    card = r.status_for_condition("heart_disease")[0]
    assert card["available"] is False and card["training_status"] == "untrained"
    with pytest.raises(SpecialistUnavailableError):
        r.route("heart_disease", {"vitals": {"features": features()}})


def test_finding_carries_status_card_and_marks_fallback(router):
    f = router.route("heart_disease", {"vitals": {"features": features()}}).findings[0]
    for k in ("model_name", "model_version", "is_stub", "is_fallback", "training_status", "feature_names"):
        assert k in f.status
    assert f.status["feature_names"] == FIELDS
    assert f.status["is_stub"] is False and f.status["is_fallback"] is True and f.status["training_status"] == "demo_fit"
    assert f.prediction.is_fallback is True and f.prediction.training_status == "demo_fit"


def test_stub_specialist_is_marked_stub_and_fallback(router):
    card = router.status_for_condition("pneumonia")[0]
    assert card["is_stub"] is True and card["is_fallback"] is True and card["training_status"] == "none"
    f = router.route("pneumonia", {"chest_xray": {"image": None}}).findings[0]
    assert f.prediction.is_stub is True and f.prediction.is_fallback is True
    assert f.prediction.metadata["stands_in_for"]


def test_shap_contributions_are_labelled_with_the_models_feature_names(router):
    rep = router.route("heart_disease", {"vitals": {"features": features()}})
    shap_exp = next(e for e in rep.findings[0].explanations if e.method == "shap")
    assert list(shap_exp.details) == FIELDS
    assert shap_exp.metadata["data_driven"] is True and "positive class" in shap_exp.metadata["explained_output"]


def test_shap_refuses_to_label_when_names_do_not_match(router):
    class Broken:
        name = "broken"
        feature_names = ["a", "b"]
        model = router.specialists["vitals"].model
    with pytest.raises(ValueError, match="cannot label SHAP values"):
        shap_mod.ShapExplainer().explain(Broken(), {"features": features()}, type("P", (), {"label": "x"})())


def test_unavailable_explainer_is_recorded_not_silently_skipped(router, monkeypatch):
    monkeypatch.setattr(shap_mod, "SHAP_AVAILABLE", False)
    rep = router.route("heart_disease", {"vitals": {"features": features()}})
    assert not any(e.method == "shap" for e in rep.findings[0].explanations)
    assert any(":shap:" in u for u in rep.unresolved_explainers)


def test_knowledge_graph_is_a_reference_lookup_not_a_data_explanation(router):
    rep = router.route("heart_disease", {"vitals": {"features": features()}})
    kg = next(e for e in rep.findings[0].explanations if e.method == "knowledge_graph")
    assert kg.metadata == {"data_driven": False, "kind": "reference_lookup"}
    assert "glucose" not in kg.summary.lower()


def test_synthetic_demo_specialists_are_labelled_as_such(router):
    for sid in ("genomic_breast_cancer", "genomic_leukemia", "cbc_leukemia"):
        card = router.specialists[sid].describe()
        assert card["training_status"] == "synthetic_demo" and card["is_fallback"] is True


def test_specialists_not_supplied_are_skipped_not_invented(router):
    rep = router.route("leukemia", {"cbc_leukemia": {"features": [0.1] * 8}})
    assert [f.specialist_id for f in rep.findings] == ["cbc_leukemia"]

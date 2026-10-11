"""Hospital-scoped append-only analysis history and review linkage."""
import logging

import pytest

import secsupport as sx
import models
from secsupport import client, bearer


@pytest.fixture(autouse=True)
def _fresh_cookies():
    client.cookies.clear()
    yield
    client.cookies.clear()


@pytest.fixture
def world():
    ha, hb = sx.make_hospital_row(), sx.make_hospital_row()
    w = {"ha": ha, "hb": hb}
    w["doc_a_id"], w["doc_a"] = sx.make_user(models.Role.CLINICIAN, ha)
    w["doc_b_id"], w["doc_b"] = sx.make_user(models.Role.CLINICIAN, hb)
    return w


def _case(token, ref="PAT-ANALYSIS"):
    return client.post(
        "/cases",
        headers=bearer(token),
        json={
            "patient_ref": ref,
            "admission_reason": "synthetic test fixture",
            "current_condition": "heart_disease",
            "presenting_symptoms": [],
        },
    ).json()["id"]


def _analysis_payload(**overrides):
    payload = {
        "model_version": "demo-v1",
        "model_status": "FALLBACK",
        "artifact_hash": None,
        "inputs_used": ["systolic_bp"],
        "missing_inputs": ["temperature_c"],
        "output": {
            "condition_key": "heart_disease",
            "prediction_label": "high_risk",
            "confidence": 0.7,
            "requires_clinician_review": True,
            "contributions": [{"feature": "systolic_bp", "value": 150, "contribution": 0.2}],
            "considerations": [{
                "rule_id": "heart-disease-review-context-v1",
                "version": "1.0.0",
                "source": "docs/MVP_SCOPE.md",
                "validation_status": "unvalidated - for clinician review",
            }],
        },
    }
    payload.update(overrides)
    return payload


def _create_analysis(token, case_id, payload=None):
    return client.post(
        f"/cases/{case_id}/analyses",
        headers=bearer(token),
        json=payload or _analysis_payload(),
    )


def test_analysis_write_and_history_are_hospital_scoped(world):
    case_id = _case(world["doc_a"])
    payload = _analysis_payload()
    create = _create_analysis(world["doc_a"], case_id, payload)
    assert create.status_code == 201, create.text
    analysis_id = create.json()["analysis_id"]

    history = client.get(f"/cases/{case_id}/analyses", headers=bearer(world["doc_a"]))
    assert history.status_code == 200
    assert [row["analysis_id"] for row in history.json()] == [analysis_id]
    assert history.json()[0]["hospital_id"] == world["ha"]
    assert history.json()[0]["created_by"] == world["doc_a_id"]
    assert history.json()[0]["output"] == payload["output"]

    # Neither endpoint accepts a request-supplied hospital scope.
    assert client.get(f"/cases/{case_id}/analyses?hospital_id={world['hb']}",
                     headers=bearer(world["doc_a"])).status_code == 200


def test_analysis_accepts_class_labels_from_the_promoted_model(world):
    case_id = _case(world["doc_a"])
    payload = _analysis_payload()
    payload["output"]["prediction_label"] = "class 1"
    response = _create_analysis(world["doc_a"], case_id, payload)
    assert response.status_code == 201, response.text
    assert response.json()["output"]["prediction_label"] == "class 1"


def test_cross_hospital_analysis_create_and_history_are_refused(world):
    case_id = _case(world["doc_a"])
    assert _create_analysis(world["doc_b"], case_id).status_code == 403
    assert client.get(f"/cases/{case_id}/analyses", headers=bearer(world["doc_b"])).status_code == 403


def test_analyses_are_append_only_and_review_links_to_analysis(world):
    case_id = _case(world["doc_a"])
    created = _create_analysis(world["doc_a"], case_id)
    assert created.status_code == 201
    analysis_id = created.json()["analysis_id"]

    update = client.put(f"/cases/{case_id}/analyses/{analysis_id}",
                        headers=bearer(world["doc_a"]), json=_analysis_payload())
    assert update.status_code in (404, 405)
    delete = client.delete(f"/cases/{case_id}/analyses/{analysis_id}",
                           headers=bearer(world["doc_a"]))
    assert delete.status_code in (404, 405)
    assert len(client.get(f"/cases/{case_id}/analyses", headers=bearer(world["doc_a"])).json()) == 1

    second = _create_analysis(world["doc_a"], case_id)
    assert second.status_code == 201 and second.json()["analysis_id"] != analysis_id
    assert len(client.get(f"/cases/{case_id}/analyses", headers=bearer(world["doc_a"])).json()) == 2

    review = client.post(f"/cases/{case_id}/review", headers=bearer(world["doc_a"]),
                         json={"decision": "ACCEPTED", "analysis_id": analysis_id})
    assert review.status_code == 201, review.text
    assert review.json()["analysis_id"] == analysis_id
    stored = client.get(f"/cases/{case_id}/reviews", headers=bearer(world["doc_a"])).json()
    assert stored[0]["analysis_id"] == analysis_id


def test_review_cannot_link_another_hospitals_analysis(world):
    case_a = _case(world["doc_a"], "PAT-ANALYSIS-A")
    case_b = _case(world["doc_b"], "PAT-ANALYSIS-B")
    analysis = _create_analysis(world["doc_b"], case_b)
    assert analysis.status_code == 201
    response = client.post(
        f"/cases/{case_a}/review",
        headers=bearer(world["doc_a"]),
        json={"decision": "ACCEPTED", "analysis_id": analysis.json()["analysis_id"]},
    )
    assert response.status_code == 403


def test_analysis_payload_rejects_unstructured_free_text_and_audit_logs_ids_only(world, caplog):
    case_id = _case(world["doc_a"])
    payload = _analysis_payload()
    payload["output"]["raw_text"] = "UNIQUE-RAW-PATIENT-TEXT"
    with caplog.at_level(logging.INFO, logger="fedheal.audit"):
        response = _create_analysis(world["doc_a"], case_id, payload)
    assert response.status_code == 422
    assert "UNIQUE-RAW-PATIENT-TEXT" not in caplog.text

    with caplog.at_level(logging.INFO, logger="fedheal.audit"):
        created = _create_analysis(world["doc_a"], case_id)
    assert created.status_code == 201
    events = [r.getMessage() for r in caplog.records if r.name == "fedheal.audit"]
    assert any('"action":"analysis.create"' in event and '"case_id":"' + case_id + '"' in event
               for event in events)
    assert "UNIQUE-RAW-PATIENT-TEXT" not in "\n".join(events)


def test_analysis_accepts_only_identifiers_and_cannot_disable_clinician_review(world):
    case_id = _case(world["doc_a"])
    payload = _analysis_payload()
    payload["inputs_used"] = ["patient reported chest discomfort"]
    assert _create_analysis(world["doc_a"], case_id, payload).status_code == 422

    payload = _analysis_payload()
    payload["output"]["requires_clinician_review"] = False
    assert _create_analysis(world["doc_a"], case_id, payload).status_code == 422

    payload = _analysis_payload()
    payload["output"]["prediction_label"] = "take aspirin 81 mg"
    assert _create_analysis(world["doc_a"], case_id, payload).status_code == 422

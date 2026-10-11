"""Module 8 persists only structured decision-support metadata in Module 1."""
import asyncio

import main


def test_persistence_forwards_only_ids_feature_metadata_and_structured_output(monkeypatch):
    calls = {}

    class Response:
        status_code = 201

        @staticmethod
        def json():
            return {"analysis_id": "analysis-123"}

    class FakeClient:
        def __init__(self, **kwargs):
            calls["timeout"] = kwargs["timeout"]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, *, json, headers):
            calls.update(url=url, payload=json, headers=headers)
            return Response()

    monkeypatch.setattr(main.httpx, "AsyncClient", FakeClient)
    packet = {
        "condition": "heart_disease",
        "model": {
            "version": "v1", "status": "DEPLOYED",
            "provenance": {"artifact_hash": "a" * 64},
        },
        "reasoning": {
            "input_drivers": [
                {"source": "vitals", "used_by_model": True, "fields": ["systolic_bp"]},
                {"source": "medical_history", "used_by_model": False},
            ],
            "missing_inputs": {"features": [], "modalities": ["scan"]},
        },
        "explanation": {"contributions": [
            {"feature": "systolic_bp", "value": 150, "contribution": 0.25},
        ]},
        "risk_assessment": {"label": "1"},
        "confidence": 0.75,
        "suggested_considerations": {"items": [{
            "id": "rule-v1", "version": "1.0.0", "source": "docs/MVP_SCOPE.md",
            "validation_status": "unvalidated - for clinician review",
            "text": "This must not be persisted.",
        }]},
    }

    result = asyncio.run(main.persist_case_analysis("case-123", "session-token", packet))
    assert result == "analysis-123"
    assert calls["url"].endswith("/cases/case-123/analyses")
    assert calls["headers"] == {"Authorization": "Bearer session-token"}
    assert calls["payload"] == {
        "model_version": "v1",
        "model_status": "DEPLOYED",
        "artifact_hash": "a" * 64,
        "inputs_used": ["systolic_bp"],
        "missing_inputs": ["scan"],
        "output": {
            "condition_key": "heart_disease",
            "prediction_label": "1",
            "confidence": 0.75,
            "requires_clinician_review": True,
            "contributions": [{"feature": "systolic_bp", "value": 150, "contribution": 0.25}],
            "considerations": [{
                "rule_id": "rule-v1", "version": "1.0.0", "source": "docs/MVP_SCOPE.md",
                "validation_status": "unvalidated - for clinician review",
            }],
        },
    }

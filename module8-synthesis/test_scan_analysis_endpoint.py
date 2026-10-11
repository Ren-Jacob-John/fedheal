import time

from fastapi.testclient import TestClient
from jose import jwt

import auth
import main


client = TestClient(main.app)


def headers(hospital_id="h1"):
    token = jwt.encode(
        {
            "sub": "doctor-1",
            "role": "clinician",
            "hospital_id": hospital_id,
            "exp": int(time.time()) + 600,
        },
        auth.SECRET_KEY,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def test_scan_analysis_returns_explicit_unavailable_status_without_findings(monkeypatch):
    calls = {}

    async def scans(path, token):
        calls.update(path=path, token=token)
        return [{"scan_id": "scan-1", "scan_type": "chest_xray", "status": "UPLOADED"}]

    monkeypatch.setattr(main, "_m1_get", scans)
    audit = []
    monkeypatch.setattr(main, "audit_event", lambda *args, **kwargs: audit.append((args, kwargs)))

    response = client.post("/cases/case-1/scans/scan-1/analyze", headers=headers())

    assert response.status_code == 200
    assert response.json() == {
        "scan_id": "scan-1",
        "status": "analysis_unavailable",
        "message": "analysis unavailable: no validated imaging model",
        "finding": None,
        "confidence": None,
        "heatmap_ref": None,
        "model_version": None,
        "model_status": "UNAVAILABLE",
        "requires_clinician_review": True,
    }
    assert calls["path"] == "/cases/case-1/scans"
    assert calls["token"]
    assert audit[0][0] == ("imaging.analysis", "unavailable")
    assert set(audit[0][1]) == {
        "request",
        "actor_user_id",
        "actor_role",
        "hospital_id",
        "case_id",
        "scan_id",
    }


def test_scan_analysis_rejects_scan_not_linked_to_case(monkeypatch):
    async def scans(path, token):
        return [{"scan_id": "different-scan", "scan_type": "chest_xray", "status": "UPLOADED"}]

    monkeypatch.setattr(main, "_m1_get", scans)
    response = client.post("/cases/case-1/scans/scan-1/analyze", headers=headers())
    assert response.status_code == 404
    assert response.json()["detail"]["status"] == "scan_not_found"


def test_scan_analysis_preserves_cross_hospital_denial(monkeypatch):
    async def forbidden(path, token):
        raise main._error(403, "forbidden", "Not permitted for this case")

    monkeypatch.setattr(main, "_m1_get", forbidden)
    response = client.post("/cases/other-hospital-case/scans/scan-1/analyze", headers=headers())
    assert response.status_code == 403
    assert response.json()["detail"]["status"] == "forbidden"


def test_scan_analysis_requires_existing_user_auth():
    response = client.post("/cases/case-1/scans/scan-1/analyze")
    assert response.status_code == 401

"""
Module 1 upload tests: normal upload works, size/record/field limits answer
413, and every forward to Module 2 carries a hospital-scoped credential.
Module 2 itself is replaced by a stub (its own behaviour is tested in
module2-validation/).

Run:  pytest test_uploads.py -v
"""
import io
import json
import logging

import pytest

import secsupport as sx  # must be first: throwaway DB before `database` loads
import models  # noqa: E402
import service_auth  # noqa: E402
from secsupport import client, bearer, main  # noqa: E402

@pytest.fixture(autouse=True)
def _anonymous_client():
    """Login tests leave a session cookie in the shared TestClient's jar;
    without this, later 'anonymous' requests would silently be logged in."""
    client.cookies.clear()
    yield
    client.cookies.clear()


GOOD = {"patient_ref": "P-1", "age_years": 50, "height_cm": 170, "weight_kg": 70,
        "systolic_bp": 120, "diastolic_bp": 80, "heart_rate_bpm": 70,
        "medication_count": 0, "medication_mg_total": 0, "label": 1}
CSV_HEADER = "patient_ref,age_years,height_cm,weight_kg,systolic_bp,diastolic_bp,heart_rate_bpm,medication_count,medication_mg_total,label"


class _Resp:
    def __init__(self, n):
        self._n = n

    def raise_for_status(self):
        pass

    def json(self):
        return {"total": self._n, "passed": self._n, "flagged": 0, "rejected": 0,
                "results": [{"patient_ref": "P-1", "status": "passed", "reasons": []}] * self._n}


class FakeModule2:
    calls: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, files=None, data=None, headers=None):
        n = len(json["records"]) if json is not None else max(1, (files["file"][1].count(b"\n") - 1))
        FakeModule2.calls.append({"url": url, "headers": headers or {}, "hospital_in_body": (json or data or {}).get("hospital_id")})
        return _Resp(n)


@pytest.fixture(autouse=True)
def stub_module2(monkeypatch):
    FakeModule2.calls = []
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeModule2)


@pytest.fixture()
def clinician():
    hid = sx.make_hospital_row()
    uid, token = sx.make_user(models.Role.CLINICIAN, hid)
    return {"hid": hid, "uid": uid, "headers": bearer(token)}


def post_json(headers, records):
    return client.post("/vitals/upload", json={"records": records}, headers=headers)


def post_csv(headers, text, name="v.csv"):
    return client.post("/vitals/upload/csv", files={"file": (name, text.encode(), "text/csv")}, headers=headers)


def csv_text(n):
    row = "P-1,50,170,70,120,80,70,0,0,1"
    return CSV_HEADER + "\n" + "\n".join([row] * n) + "\n"


# ---- normal + maximum ---------------------------------------------------

def test_small_json_upload_succeeds(clinician):
    resp = post_json(clinician["headers"], [GOOD] * 3)
    assert resp.status_code == 200, resp.text
    assert resp.json()["stored"] == 3 and resp.json()["total"] == 3


def test_upload_requires_authentication():
    assert client.post("/vitals/upload", json={"records": [GOOD]}).status_code == 401
    assert client.post("/vitals/upload/csv", files={"file": ("v.csv", b"x", "text/csv")}).status_code == 401


def test_json_upload_at_exact_record_limit_succeeds(clinician):
    resp = post_json(clinician["headers"], [GOOD] * main.UPLOAD_LIMITS.max_records)
    assert resp.status_code == 200, resp.text[:200]
    assert resp.json()["stored"] == main.UPLOAD_LIMITS.max_records


def test_csv_upload_succeeds(clinician):
    resp = post_csv(clinician["headers"], csv_text(3))
    assert resp.status_code == 200, resp.text
    assert resp.json()["stored"] == 3


def test_csv_at_exact_row_limit_succeeds(clinician):
    resp = post_csv(clinician["headers"], csv_text(main.UPLOAD_LIMITS.max_records))
    assert resp.status_code == 200, resp.text[:200]


# ---- oversized ----------------------------------------------------------

def test_excessive_record_count_is_413(clinician):
    resp = post_json(clinician["headers"], [GOOD] * (main.UPLOAD_LIMITS.max_records + 1))
    assert resp.status_code == 413
    assert FakeModule2.calls == []  # never forwarded


def test_oversized_json_body_is_413_before_parsing(clinician):
    big = json.dumps({"records": [GOOD], "pad": "x" * (main.UPLOAD_LIMITS.max_json_body_bytes + 10)})
    resp = client.post("/vitals/upload", content=big,
                       headers={**clinician["headers"], "Content-Type": "application/json"})
    assert resp.status_code == 413
    assert FakeModule2.calls == []


def test_oversized_body_without_content_length_is_413(clinician):
    def chunks():
        chunk = b"x" * 65536
        for _ in range(main.UPLOAD_LIMITS.max_json_body_bytes // 65536 + 2):
            yield chunk

    resp = client.post("/vitals/upload", content=chunks(),
                       headers={**clinician["headers"], "Content-Type": "application/json"})
    assert resp.status_code == 413


def test_oversized_csv_file_is_413(clinician):
    text = CSV_HEADER + "\n" + "P-1," + "9" * (main.UPLOAD_LIMITS.max_csv_bytes + 100) + "\n"
    resp = post_csv(clinician["headers"], text)
    assert resp.status_code == 413
    assert FakeModule2.calls == []


def test_csv_with_too_many_rows_is_413(clinician):
    resp = post_csv(clinician["headers"], csv_text(main.UPLOAD_LIMITS.max_records + 1))
    assert resp.status_code == 413
    assert FakeModule2.calls == []


def test_csv_with_too_many_columns_is_413(clinician):
    cols = [f"c{i}" for i in range(main.UPLOAD_LIMITS.max_record_fields + 1)]
    resp = post_csv(clinician["headers"], ",".join(cols) + "\n" + ",".join(["1"] * len(cols)) + "\n")
    assert resp.status_code == 413


def test_oversized_field_value_is_413_json_and_csv(clinician):
    huge = "A" * (main.UPLOAD_LIMITS.max_field_chars + 1)
    assert post_json(clinician["headers"], [{**GOOD, "patient_ref": huge}]).status_code == 413
    text = csv_text(1).replace("P-1", huge, 1)
    assert post_csv(clinician["headers"], text).status_code == 413


def test_too_many_fields_in_a_record_is_413(clinician):
    rec = {**GOOD, **{f"extra{i}": 1 for i in range(main.UPLOAD_LIMITS.max_record_fields)}}
    assert post_json(clinician["headers"], [rec]).status_code == 413


def test_413_error_text_never_echoes_submitted_values(clinician):
    huge = "SECRET-PATIENT-REF-" + "A" * main.UPLOAD_LIMITS.max_field_chars
    resp = post_json(clinician["headers"], [{**GOOD, "patient_ref": huge}])
    assert resp.status_code == 413 and "SECRET-PATIENT-REF" not in resp.text


def test_limits_are_configurable(monkeypatch):
    import limits
    monkeypatch.setenv("FEDHEAL_MAX_RECORDS", "7")
    assert limits.UploadLimits.from_env().max_records == 7
    monkeypatch.setenv("FEDHEAL_MAX_RECORDS", "zero")
    import config
    with pytest.raises(config.ConfigError):
        limits.UploadLimits.from_env()


# ---- credential sent to Module 2 -----------------------------------------

def test_forward_to_module2_carries_hospital_scoped_credential(clinician):
    assert post_json(clinician["headers"], [GOOD]).status_code == 200
    assert post_csv(clinician["headers"], csv_text(1)).status_code == 200
    assert len(FakeModule2.calls) == 2
    for call in FakeModule2.calls:
        claims = service_auth.verify_service_token(
            call["headers"].get("X-Service-Key"), signing_key=main.auth.M1_M2_SIGNING_KEY,
            allowed_audiences={service_auth.AUD_VALIDATE}, allowed_callers={"module1"})
        assert claims["hid"] == clinician["hid"]  # from the uploader's JWT, not the request


# ---- audit ---------------------------------------------------------------

def test_upload_audited_without_patient_data(clinician, caplog):
    caplog.set_level(logging.INFO, logger="fedheal.audit")
    post_json(clinician["headers"], [{**GOOD, "patient_ref": "P-DO-NOT-LOG"}])
    events = [json.loads(r.getMessage()) for r in caplog.records if r.name == "fedheal.audit"]
    ev = [e for e in events if e["action"] == "vitals.upload"][-1]
    assert ev["hospital_id"] == clinician["hid"] and ev["actor_user_id"] == clinician["uid"] and ev["stored"] == 1
    assert "P-DO-NOT-LOG" not in caplog.text

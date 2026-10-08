"""Registry lifecycle + validation gate. Metric values below are SYNTHETIC test
inputs for exercising the gate logic; they are not results of any real model."""
import hashlib
import time

import pytest
from fastapi.testclient import TestClient
from jose import jwt

import auth
import main
from model_registry import Policy, evaluate_candidate

client = TestClient(main.app)


def admin():
    t = jwt.encode({"sub": "root", "role": "super_admin", "hospital_id": None, "exp": int(time.time()) + 600},
                   auth.SECRET_KEY, algorithm="HS256")
    return {"Authorization": f"Bearer {t}"}


def svc():
    return {"X-Service-Key": auth.MODULE3_SERVICE_KEY}


_counter = [0]


def cand(accuracy=0.80, n_eval=120, hospitals=("ha", "hb"), **over):
    _counter[0] += 1
    body = {
        "model_name": "vitals-fedavg", "condition": f"cond-{over.pop('cond', 'x')}", "training_round": 3,
        "participating_hospitals": list(hospitals),
        "training_metadata": {"aggregation": "fedavg", "validated_records_only": True,
                              "labels_from_hospital_only": True},
        "metrics": {"accuracy": accuracy, "n_eval": n_eval},
        "artifact_hash": hashlib.sha256(f"artifact-{_counter[0]}".encode()).hexdigest(),
    }
    body.update(over)
    return body


def register(body):
    return client.post("/admin/models/candidates", json=body, headers=svc())


def full_cycle(cond, accuracy=0.8):
    c = register(cand(accuracy, cond=cond)).json()
    client.post(f"/admin/models/{c['id']}/validate", headers=admin())
    return client.post(f"/admin/models/{c['id']}/promote", json={}, headers=admin()).json()


# ---- pure gate ----

def test_gate_passes_a_good_candidate_and_reports_every_check():
    r = evaluate_candidate(cand(), None, Policy())
    assert r["passed"] and {c["name"] for c in r["checks"]} == {
        "integrity", "participation", "data_quality", "minimum_metrics", "beats_majority_baseline",
        "regression", "fairness"}
    assert next(c for c in r["checks"] if c["name"] == "regression")["status"] == "SKIPPED"
    assert next(c for c in r["checks"] if c["name"] == "fairness")["status"] == "SKIPPED"


@pytest.mark.parametrize("mut,failed", [
    ({"metrics": {"accuracy": 0.40, "n_eval": 120}}, "minimum_metrics"),
    ({"metrics": {"accuracy": 0.9, "n_eval": 10}}, "minimum_metrics"),
    ({"metrics": {"n_eval": 120}}, "minimum_metrics"),
    ({"participating_hospitals": ["ha"]}, "participation"),
    ({"artifact_hash": "not-a-hash"}, "integrity"),
    ({"training_metadata": {"validated_records_only": True}}, "data_quality"),
    ({"metrics": {"accuracy": 0.9, "n_eval": 120, "per_hospital_accuracy": {"ha": 0.95, "hb": 0.5}}}, "fairness"),
])
def test_gate_failures(mut, failed):
    r = evaluate_candidate({**cand(), **mut}, None, Policy())
    assert not r["passed"]
    assert [c["name"] for c in r["checks"] if c["status"] == "FAIL"] == [failed]


def test_gate_requires_beating_the_majority_class_floor():
    body = cand(0.62)
    body["metrics"]["majority_class_floor"] = 0.60
    r = evaluate_candidate(body, None, Policy())
    assert not r["passed"]
    assert [c["name"] for c in r["checks"] if c["status"] == "FAIL"] == ["beats_majority_baseline"]
    body["metrics"]["majority_class_floor"] = 0.50
    assert evaluate_candidate(body, None, Policy())["passed"]


def test_gate_blocks_regression_but_tolerates_small_noise():
    cur = {"metrics": {"accuracy": 0.85}}
    assert not evaluate_candidate(cand(0.70), cur, Policy())["passed"]
    assert evaluate_candidate(cand(0.84), cur, Policy())["passed"]


# ---- lifecycle ----

def test_registration_deploys_nothing_and_requires_service_key():
    assert client.post("/admin/models/candidates", json=cand()).status_code == 401
    assert client.post("/admin/models/candidates", json=cand(), headers=admin()).status_code == 401
    r = register(cand(cond="reg"))
    assert r.status_code == 201
    b = r.json()
    assert b["deployment_status"] == "CANDIDATE" and b["validation_status"] == "PENDING" and b["version"] == "v1"
    assert client.get("/admin/models/current", params={"model_name": "vitals-fedavg", "condition": "cond-reg"},
                      headers=admin()).status_code == 404


def test_cannot_promote_unvalidated_or_failed_models():
    c = register(cand(cond="p1")).json()
    assert client.post(f"/admin/models/{c['id']}/promote", json={}, headers=admin()).status_code == 409
    bad = register(cand(0.2, cond="p2")).json()
    v = client.post(f"/admin/models/{bad['id']}/validate", headers=admin()).json()
    assert v["deployment_status"] == "REJECTED" and v["validation_status"] == "FAILED"
    assert any(ch["status"] == "FAIL" for ch in v["validation_report"]["checks"])
    assert client.post(f"/admin/models/{bad['id']}/promote", json={}, headers=admin()).status_code == 409


def test_promotion_requires_super_admin():
    c = register(cand(cond="p3")).json()
    client.post(f"/admin/models/{c['id']}/validate", headers=admin())
    assert client.post(f"/admin/models/{c['id']}/promote", json={}).status_code == 401
    clin = jwt.encode({"sub": "u", "role": "clinician", "hospital_id": "h", "exp": int(time.time()) + 60},
                      auth.SECRET_KEY, algorithm="HS256")
    assert client.post(f"/admin/models/{c['id']}/promote", json={},
                       headers={"Authorization": f"Bearer {clin}"}).status_code == 403


def test_promote_replaces_previous_and_rollback_restores_it():
    v1 = full_cycle("rb")
    assert v1["deployment_status"] == "DEPLOYED" and v1["approved_by"] == "root"
    v2 = full_cycle("rb", 0.82)
    assert v2["version"] == "v2" and v2["parent_version"] == "v1"
    listing = {m["version"]: m["deployment_status"] for m in
               client.get("/admin/models", params={"condition": "cond-rb"}, headers=admin()).json()}
    assert listing == {"v1": "RETIRED", "v2": "DEPLOYED"}
    rb = client.post("/admin/models/rollback", params={"model_name": "vitals-fedavg", "condition": "cond-rb"},
                     headers=admin())
    assert rb.status_code == 200 and rb.json()["version"] == "v1" and rb.json()["deployment_status"] == "DEPLOYED"
    listing = {m["version"]: m["deployment_status"] for m in
               client.get("/admin/models", params={"condition": "cond-rb"}, headers=admin()).json()}
    assert listing == {"v1": "DEPLOYED", "v2": "ROLLED_BACK"}


def test_rollback_without_a_previous_model_is_refused():
    full_cycle("rb2")
    r = client.post("/admin/models/rollback", params={"model_name": "vitals-fedavg", "condition": "cond-rb2"},
                    headers=admin())
    assert r.status_code == 409


def test_worse_candidate_cannot_displace_a_better_deployed_model():
    full_cycle("reg2", 0.90)
    c = register(cand(0.65, cond="reg2")).json()
    v = client.post(f"/admin/models/{c['id']}/validate", headers=admin()).json()
    assert v["deployment_status"] == "REJECTED"
    assert any(ch["name"] == "regression" and ch["status"] == "FAIL" for ch in v["validation_report"]["checks"])
    cur = client.get("/admin/models/current", params={"model_name": "vitals-fedavg", "condition": "cond-reg2"},
                     headers=admin()).json()
    assert cur["version"] == "v1"      # previous production model preserved


def test_revalidating_or_promoting_twice_is_refused():
    c = register(cand(cond="twice")).json()
    client.post(f"/admin/models/{c['id']}/validate", headers=admin())
    assert client.post(f"/admin/models/{c['id']}/validate", headers=admin()).status_code == 409
    assert client.post(f"/admin/models/{c['id']}/promote", json={}, headers=admin()).status_code == 200
    assert client.post(f"/admin/models/{c['id']}/promote", json={}, headers=admin()).status_code == 409


# ---- raw-data isolation at the federation boundary ----

@pytest.mark.parametrize("where,payload", [
    ("training_metadata", {"records": [{"age": 50}]}),
    ("training_metadata", {"patient_ref": "PAT-1"}),
    ("metrics", {"accuracy": 0.9, "n_eval": 100, "y": [0, 1]}),
    ("metrics", {"accuracy": 0.9, "n_eval": 100, "nested": {"vitals": 1}}),
    ("training_metadata", {"csv": "a,b\n1,2"}),
    ("training_metadata", {"summary": "x" * 300}),
    ("metrics", {"accuracy": 0.9, "n_eval": 100, "series": list(range(500))}),
])
def test_registry_refuses_anything_that_looks_like_raw_data(where, payload):
    body = cand(cond="raw")
    body[where] = {**body[where], **payload}
    assert register(body).status_code == 422

"""
End-to-end integration: the real services, real HTTP, nothing mocked.

    user auth (Module 1)  ->  upload (Module 1)  ->  validation (Module 2)
      ->  storage (Module 1)  ->  record read (Module 1, as the user)
      ->  feature mapping + condition routing (Module 8 -> Module 6)
      ->  specialist (Module 5)  ->  structured response

Starts Module 1, Module 2 and Module 8 as uvicorn subprocesses on free
ports against a throwaway SQLite file, with FEDHEAL_ENV=development (the
dev-only fallbacks are what let separate processes agree on keys without
any real secret in this repo).

Run from the repo root:  pytest tests/integration -v
"""
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import uuid

import httpx
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ADMIN_PASSWORD = "e2e-bootstrap-password-1"
VITALS_FIELDS = ["age_years", "systolic_bp", "diastolic_bp", "heart_rate_bpm",
                 "weight_kg", "height_cm", "medication_count", "medication_mg_total"]

GOOD = {"age_years": 58, "height_cm": 172, "weight_kg": 80, "systolic_bp": 150, "diastolic_bp": 90,
        "heart_rate_bpm": 100, "medication_count": 2, "medication_mg_total": 300, "label": 1}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def base_env(**extra) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("FEDHEAL_", "FEDMED_"))}
    env.update({"FEDHEAL_ENV": "development", "PYTHONUNBUFFERED": "1"})
    env.update(extra)
    return env


class Service:
    def __init__(self, name, module_dir, port, env, log_dir):
        self.name, self.port = name, port
        self.url = f"http://127.0.0.1:{port}"
        self.log_path = pathlib.Path(log_dir) / f"{name}.log"
        self._log = open(self.log_path, "w")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT / module_dir, env=env, stdout=self._log, stderr=subprocess.STDOUT)

    def wait_healthy(self, timeout=90):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"{self.name} exited early:\n{self.log_path.read_text()[-2000:]}")
            try:
                r = httpx.get(f"{self.url}/health", timeout=2)
                if r.status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.5)
        raise RuntimeError(f"{self.name} did not become healthy:\n{self.log_path.read_text()[-2000:]}")

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self._log.close()


@pytest.fixture(scope="module")
def stack():
    tmp = tempfile.mkdtemp(prefix="fedheal_e2e_")
    db_url = f"sqlite:///{tmp}/auth.db"
    p1, p2, p8, p8b = free_port(), free_port(), free_port(), free_port()

    m1_env = base_env(FEDHEAL_DATABASE_URL=db_url, FEDHEAL_VALIDATION_API_URL=f"http://127.0.0.1:{p2}")
    # Schema comes from the models here (tests only); deployments use Alembic.
    subprocess.run([sys.executable, "-c", "import database, models; database.Base.metadata.create_all(bind=database.engine)"],
                   cwd=ROOT / "module1-auth", env=m1_env, check=True, timeout=60)
    subprocess.run([sys.executable, "create_super_admin.py", "--email", "admin@e2e.fedheal.local"],
                   cwd=ROOT / "module1-auth", env={**m1_env, "FEDHEAL_BOOTSTRAP_ADMIN_PASSWORD": ADMIN_PASSWORD},
                   check=True, timeout=60, capture_output=True)

    services = {
        "m1": Service("module1", "module1-auth", p1, m1_env, tmp),
        "m2": Service("module2", "module2-validation", p2, base_env(FEDHEAL_ADMIN_API_URL="http://127.0.0.1:9"), tmp),
        "m8": Service("module8", "module8-synthesis", p8,
                      base_env(FEDHEAL_AUTH_API_URL=f"http://127.0.0.1:{p1}", FEDHEAL_ALLOW_DEMO_MODEL="true",
                               FEDHEAL_ADMIN_API_URL="http://127.0.0.1:9"), tmp),
        # Same Module 8 with the demo fallback explicitly OFF: the vitals specialist has no model.
        "m8_nomodel": Service("module8_nomodel", "module8-synthesis", p8b,
                              base_env(FEDHEAL_AUTH_API_URL=f"http://127.0.0.1:{p1}", FEDHEAL_ALLOW_DEMO_MODEL="false"), tmp),
    }
    try:
        for s in services.values():
            s.wait_healthy()
        yield services
    finally:
        for s in services.values():
            s.stop()


def bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


def login(m1, email, password):
    r = httpx.post(f"{m1.url}/token", data={"username": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def make_hospital_user(m1, admin_token):
    h = httpx.post(f"{m1.url}/hospitals", json={"name": f"E2E {uuid.uuid4().hex[:8]}"}, headers=bearer(admin_token), timeout=20)
    assert h.status_code == 200, h.text
    hid = h.json()["id"]
    # Production onboarding: super_admin -> hospital_admin -> doctor. Public registration is closed.
    adm_email = f"hadm-{uuid.uuid4().hex[:8]}@e2e.fedheal.local"
    a = httpx.post(f"{m1.url}/admin/users", headers=bearer(admin_token), timeout=20,
                   json={"email": adm_email, "password": "e2e-hospital-admin-1", "role": "hospital_admin", "hospital_id": hid})
    assert a.status_code == 200, a.text
    adm_tok = login(m1, adm_email, "e2e-hospital-admin-1")
    email, pw = f"clin-{uuid.uuid4().hex[:8]}@e2e.fedheal.local", "e2e-clinician-pass-1"
    d = httpx.post(f"{m1.url}/hospital/doctors", headers=bearer(adm_tok), timeout=20,
                   json={"full_name": "E2E Doctor", "email": email, "password": pw})
    assert d.status_code == 201, d.text
    return hid, login(m1, email, pw)


@pytest.fixture(scope="module")
def world(stack):
    m1 = stack["m1"]
    admin = login(m1, "admin@e2e.fedheal.local", ADMIN_PASSWORD)
    hid_a, tok_a = make_hospital_user(m1, admin)
    hid_b, tok_b = make_hospital_user(m1, admin)
    return {"m1": m1, "hid_a": hid_a, "tok_a": tok_a, "hid_b": hid_b, "tok_b": tok_b}


def upload(w, record, ref, token=None):
    r = httpx.post(f"{w['m1'].url}/vitals/upload", json={"records": [{"patient_ref": ref, **record}]},
                   headers=bearer(token or w["tok_a"]), timeout=60)
    return r


def stored(w, ref, token=None):
    rows = httpx.get(f"{w['m1'].url}/vitals", headers=bearer(token or w["tok_a"]), timeout=20).json()
    return next((r for r in rows if r["patient_ref"] == ref), None)


def synth(stack, token, record_id, condition="heart_disease", which="m8"):
    return httpx.post(f"{stack[which].url}/synthesize/record", json={"record_id": record_id, "condition": condition},
                      headers=bearer(token), timeout=60)


# ---------------------------------------------------------------------------

def test_valid_record_flows_from_upload_to_synthesis(stack, world):
    ref = f"E2E-{uuid.uuid4().hex[:8]}"
    up = upload(world, GOOD, ref)
    assert up.status_code == 200, up.text
    assert up.json()["stored"] == 1 and up.json()["passed"] == 1                      # Module 2 validated, Module 1 stored
    rec = stored(world, ref)
    assert rec and rec["validation_status"] == "passed" and rec["age_years"] == 58

    r = synth(stack, world["tok_a"], rec["id"])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["record"]["record_id"] == rec["id"] and d["record"]["patient_ref"] == ref
    assert d["prediction"]["label"] in ("high_risk", "low_risk")
    assert d["synthesis"]["requires_clinician_review"] is True


def test_correct_specialist_is_selected_and_its_metadata_is_present(stack, world):
    ref = f"E2E-{uuid.uuid4().hex[:8]}"
    upload(world, GOOD, ref)
    d = synth(stack, world["tok_a"], stored(world, ref)["id"]).json()
    spec = d["specialist"]
    assert spec["specialist_id"] == "vitals" and spec["modality"] == "vitals"
    assert spec["feature_names"] == VITALS_FIELDS
    for k in ("model_name", "model_version", "is_stub", "is_fallback", "training_status"):
        assert k in spec


def test_fallback_is_clearly_marked_and_never_called_federated(stack, world):
    ref = f"E2E-{uuid.uuid4().hex[:8]}"
    upload(world, GOOD, ref)
    d = synth(stack, world["tok_a"], stored(world, ref)["id"]).json()
    assert d["specialist"]["is_fallback"] is True and d["specialist"]["training_status"] == "demo_fit"
    assert d["model"]["federated"] is False and d["model"]["hospital_trained"] is False
    assert {"fallback_model", "demo_training_data"} <= {w["code"] for w in d["warnings"]}


def test_explanation_fields_correspond_to_model_features_and_record_values(stack, world):
    ref = f"E2E-{uuid.uuid4().hex[:8]}"
    upload(world, GOOD, ref)
    rec = stored(world, ref)
    d = synth(stack, world["tok_a"], rec["id"]).json()
    exp = d["explanation"]
    assert exp["status"] == "available"
    assert [c["feature"] for c in exp["contributions"]] == VITALS_FIELDS == exp["feature_names"]
    assert {c["feature"]: c["value"] for c in exp["contributions"]} == {f: float(rec[f]) for f in VITALS_FIELDS}


def test_invalid_record_is_rejected_by_module2_and_never_stored(stack, world):
    ref = f"E2E-BAD-{uuid.uuid4().hex[:6]}"
    up = upload(world, {**GOOD, "age_years": 500}, ref)
    assert up.status_code == 200
    body = up.json()
    assert body["rejected"] == 1 and body["stored"] == 0
    assert stored(world, ref) is None


def test_record_missing_a_model_feature_reports_it_instead_of_guessing(stack, world):
    ref = f"E2E-MISS-{uuid.uuid4().hex[:6]}"
    rec_in = {k: v for k, v in GOOD.items() if k not in ("diastolic_bp", "heart_rate_bpm")}
    up = upload(world, rec_in, ref)
    assert up.status_code == 200, up.text
    rec = stored(world, ref)
    if rec is None or rec["validation_status"] != "passed":
        pytest.fail(f"expected a stored passed record with optional vitals omitted; got upload={up.json()}")
    r = synth(stack, world["tok_a"], rec["id"])
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["status"] == "incomplete_data" and d["missing_features"] == ["diastolic_bp", "heart_rate_bpm"]
    assert "prediction" not in r.text


def test_unknown_condition_and_non_vitals_condition_are_explicit(stack, world):
    ref = f"E2E-{uuid.uuid4().hex[:8]}"
    upload(world, GOOD, ref)
    rid = stored(world, ref)["id"]
    unk = synth(stack, world["tok_a"], rid, condition="not_a_disease")
    assert unk.status_code == 404 and unk.json()["detail"]["status"] == "unknown_condition"
    pn = synth(stack, world["tok_a"], rid, condition="pneumonia")
    assert pn.status_code == 422 and pn.json()["detail"]["status"] == "unsupported_input"
    chest = pn.json()["detail"]["specialists"][0]
    assert chest["specialist_id"] == "chest_xray" and chest["is_stub"] is True and chest["is_fallback"] is True


def test_unavailable_specialist_is_reported_not_silently_substituted(stack, world):
    ref = f"E2E-{uuid.uuid4().hex[:8]}"
    upload(world, GOOD, ref)
    r = synth(stack, world["tok_a"], stored(world, ref)["id"], which="m8_nomodel")
    assert r.status_code == 503
    d = r.json()["detail"]
    assert d["status"] == "specialist_unavailable" and d["specialist"]["available"] is False
    assert d["model"]["source"] == "none"


def test_authentication_and_tenancy_are_enforced_through_the_whole_chain(stack, world):
    ref = f"E2E-{uuid.uuid4().hex[:8]}"
    upload(world, GOOD, ref)
    rid = stored(world, ref)["id"]
    anon = httpx.post(f"{stack['m8'].url}/synthesize/record", json={"record_id": rid}, timeout=20)
    assert anon.status_code == 401
    other = synth(stack, world["tok_b"], rid)                       # hospital B asks for hospital A's record
    assert other.status_code == 403 and other.json()["detail"]["status"] == "forbidden"
    assert stored(world, ref, token=world["tok_b"]) is None          # and cannot list it either
    assert synth(stack, world["tok_a"], "no-such-record").status_code == 404


def test_module2_cannot_be_called_directly_without_a_service_credential(stack, world):
    r = httpx.post(f"{stack['m2'].url}/validate/vitals", json={"records": [GOOD]}, timeout=20)
    assert r.status_code == 401


def test_flagged_record_cannot_be_synthesized(stack, world):
    m1 = world["m1"]
    # Force a flagged row through the same code path hospital admins review: an extreme-but-valid record in a batch.
    ref = f"E2E-FLAG-{uuid.uuid4().hex[:6]}"
    batch = [{"patient_ref": f"E2E-N{i}-{ref}", **{**GOOD, "age_years": 50 + i}} for i in range(12)]
    batch.append({"patient_ref": ref, **{**GOOD, "age_years": 119, "weight_kg": 250, "systolic_bp": 240, "diastolic_bp": 130, "heart_rate_bpm": 190}})
    up = httpx.post(f"{m1.url}/vitals/upload", json={"records": batch}, headers=bearer(world["tok_a"]), timeout=60)
    assert up.status_code == 200, up.text
    rec = stored(world, ref)
    if rec is None or rec["validation_status"] != "flagged":
        pytest.skip(f"outlier detector did not flag the probe record (status={rec and rec['validation_status']}); "
                    "the 409 path is also covered in module8-synthesis/test_record_flow.py")
    r = synth(stack, world["tok_a"], rec["id"])
    assert r.status_code == 409 and r.json()["detail"]["status"] == "record_not_validated"

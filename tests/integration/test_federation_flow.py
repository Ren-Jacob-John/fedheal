"""
Two-hospital federated run against the real services, then the registry gate.

  Module 1 + Module 2 + Module 7 + Module 8 as real processes
    (throwaway local document stores)
    -> seed_uci_heart.py uploads public UCI Cleveland records for TWO hospitals
       through Module 1's front door (so they pass Module 2's validation)
    -> hospital-local watch runners: each hospital trains locally, Flower
       aggregates, and a CANDIDATE is registered with request/count provenance
    -> Module 7: candidate is NOT deployed; validation gate decides; only a
       passing model can be promoted by a super_admin.
    -> Module 8 (demo fallback DISABLED): refuses to analyse before promotion,
       and after promotion serves exactly the promoted model with its provenance.

Module 7 here runs with a deliberately RELAXED gate policy (FEDHEAL_GATE_* below) so the
small public-data run can be promoted and the promotion -> inference wiring can be
tested. Under the default policy the same run is rejected (see docs/MODEL_STATUS.md and
module7-admin/test_model_registry.py). The relaxed policy is a test setting, not a claim
that this model is good.

Data is public UCI Cleveland data (3 real features) — a demo of the pipeline,
NOT clinical evidence. This test asserts behaviour that holds whether or not the
candidate happens to clear the gate; it never assumes a particular accuracy.

Run from the repo root:  pytest tests/integration/test_federation_flow.py -v
"""
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import uuid

import httpx
import numpy as np
import pytest

from test_doctor_workflow import VITALS, make_hospital_with_doctor
from test_e2e_flow import ADMIN_PASSWORD, ROOT, Service, base_env, bearer, free_port, login

M3 = ROOT / "module3-fedlearning"


def _mint_scoped_token(hospital_id: str, audience: str, signing_key: str) -> str:
    sys.path.insert(0, str(M3))
    try:
        import service_auth
        return service_auth.mint_service_token(
            signing_key,
            caller="module3",
            audience=audience,
            hospital_id=hospital_id,
            ttl_seconds=3600,
        )
    finally:
        sys.path.remove(str(M3))


def _wait_for_flower(port: int, process: subprocess.Popen, log_path: pathlib.Path,
                     timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Flower server exited early:\n{log_path.read_text()[-3000:]}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(f"Flower server did not listen:\n{log_path.read_text()[-3000:]}")


@pytest.fixture(scope="module")
def fed():
    tmp = tempfile.mkdtemp(prefix="fedheal_fed_")
    p1, p2, p7, p8, pflower = (free_port() for _ in range(5))
    m1_env = base_env(FEDHEAL_DB_BACKEND="local", FEDHEAL_LOCAL_STORE_PATH=f"{tmp}/auth_store.json",
                      FEDHEAL_VALIDATION_API_URL=f"http://127.0.0.1:{p2}")
    subprocess.run([sys.executable, "create_super_admin.py", "--email", "admin@fed.fedheal.local"],
                   cwd=ROOT / "module1-auth", env={**m1_env, "FEDHEAL_BOOTSTRAP_ADMIN_PASSWORD": ADMIN_PASSWORD},
                   check=True, timeout=60, capture_output=True)
    services = {
        "m1": Service("module1", "module1-auth", p1, m1_env, tmp),
        "m2": Service("module2", "module2-validation", p2, base_env(FEDHEAL_ADMIN_API_URL=f"http://127.0.0.1:{p7}"), tmp),
        "m7": Service("module7", "module7-admin", p7,
                      base_env(FEDHEAL_DB_BACKEND="local", FEDHEAL_LOCAL_STORE_PATH=f"{tmp}/admin_store.json",
                               FEDHEAL_AUTH_API_URL=f"http://127.0.0.1:{p1}",
                               # TEST-ONLY relaxed gate (see module docstring)
                               FEDHEAL_GATE_MIN_ACCURACY="0.5", FEDHEAL_GATE_MIN_EVAL_EXAMPLES="30",
                               FEDHEAL_GATE_MAX_HOSPITAL_GAP="0.6", FEDHEAL_GATE_MIN_MARGIN_OVER_MAJORITY="0.0",
                               FEDHEAL_RETRAIN_MIN_ELIGIBLE_RECORDS="1"), tmp),
        # Demo fallback explicitly OFF: any answer must come from the promoted federated model.
        "m8": Service("module8", "module8-synthesis", p8,
                      base_env(FEDHEAL_AUTH_API_URL=f"http://127.0.0.1:{p1}", FEDHEAL_ADMIN_API_URL=f"http://127.0.0.1:{p7}",
                               FEDHEAL_ALLOW_DEMO_MODEL="false", FEDHEAL_PROMOTED_MODEL_CACHE_SECONDS="0"), tmp),
    }
    try:
        for s in services.values():
            s.wait_healthy()
        env = base_env(FEDHEAL_AUTH_API_URL=services["m1"].url, FEDHEAL_ADMIN_API_URL=services["m7"].url,
                       FEDHEAL_SEED_SUPER_ADMIN_EMAIL="admin@fed.fedheal.local",
                       FEDHEAL_SEED_SUPER_ADMIN_PASSWORD=ADMIN_PASSWORD,
                       FEDHEAL_MODEL_STORAGE_PATH=f"{tmp}/artifacts")
        seed = subprocess.run([sys.executable, "seed_uci_heart.py", "--hospitals", "2", "--auth-url", services["m1"].url],
                              cwd=M3, env=env, capture_output=True, text=True, timeout=300)
        assert seed.returncode == 0, seed.stdout[-1500:] + seed.stderr[-1500:]

        admin = login(services["m1"], "admin@fed.fedheal.local", ADMIN_PASSWORD)
        hospitals = httpx.get(f"{services['m1'].url}/hospitals",
                              headers=bearer(admin), timeout=20).json()
        assert len(hospitals) == 2
        runner_specs = []
        for index, hospital in enumerate(hospitals, start=1):
            hospital_id = hospital["id"]
            runner_specs.append({
                "hospital_id": hospital_id,
                "user_token": login(services["m1"], f"seed-admin-{index}@fedheal.local",
                                    "uci-seed-demo-password"),
                "queue_token": _mint_scoped_token(
                    hospital_id, "module7:retraining-runner",
                    "dev-only-signing-key-module3-to-module7",
                ),
                "vitals_token": _mint_scoped_token(
                    hospital_id, "module1:vitals-export",
                    "dev-only-signing-key-module3-to-module1",
                ),
            })

        server_port = pflower
        server_log_path = pathlib.Path(tmp) / "flower-server.log"
        server_log = open(server_log_path, "w", encoding="utf-8")
        server_env = {**env, "FEDHEAL_ADMIN_API_URL": services["m7"].url}
        server = subprocess.Popen(
            [sys.executable, "server.py", "--min-clients", "2", "--rounds", "1",
             "--address", f"127.0.0.1:{server_port}"],
            cwd=M3, env=server_env, stdout=server_log, stderr=subprocess.STDOUT,
        )
        client_logs = []
        client_processes = []
        try:
            _wait_for_flower(server_port, server, server_log_path)
            for index, spec in enumerate(runner_specs, start=1):
                log = open(pathlib.Path(tmp) / f"flower-client-{index}.log", "w", encoding="utf-8")
                client_logs.append(log)
                client_env = {
                    **env,
                    "FEDHEAL_AUTH_API_URL": services["m1"].url,
                    "FEDHEAL_ADMIN_API_URL": services["m7"].url,
                    "FEDHEAL_SVC_TOKEN_M3_M1": spec["vitals_token"],
                    "FEDHEAL_SVC_TOKEN_M3_M7": spec["queue_token"],
                }
                client_processes.append(subprocess.Popen(
                    [sys.executable, "client_runner.py", "--hospital-id", spec["hospital_id"],
                     "--server", f"127.0.0.1:{server_port}", "--min-records", "10",
                     "--watch-retraining", "--poll-seconds", "1"],
                    cwd=M3, env=client_env, stdout=log, stderr=subprocess.STDOUT,
                ))

            # Do not infer readiness from a fixed delay: loading validated
            # records happens inside each hospital process and can take
            # longer on CI. Wait for each runner's first count-only report,
            # which initializes its baseline in the fresh Module 7 store.
            baseline_deadline = time.monotonic() + 60
            hospital_ids = {spec["hospital_id"] for spec in runner_specs}
            while time.monotonic() < baseline_deadline:
                log_text = services["m7"].log_path.read_text(encoding="utf-8", errors="replace")
                reported = {
                    hospital_id for hospital_id in hospital_ids
                    if f'"action":"retraining.eligibility"' in log_text
                    and f'"target_hospital_id":"{hospital_id}"' in log_text
                }
                if reported == hospital_ids:
                    break
                if any(process.poll() not in (None, 0) for process in client_processes):
                    logs = "\n".join(
                        (pathlib.Path(tmp) / f"flower-client-{i}.log").read_text(
                            encoding="utf-8", errors="replace"
                        )[-3000:]
                        for i in (1, 2)
                    )
                    raise RuntimeError(f"A hospital runner failed before establishing its baseline:\n{logs}")
                time.sleep(0.25)
            else:
                raise RuntimeError("Hospital runners did not establish count-only retraining baselines.")

            # A batch is needed because Module 2's outlier screen can flag a
            # singleton. The named synthetic test rows are never production
            # data and only exercise the threshold-trigger path.
            for index, spec in enumerate(runner_specs, start=1):
                records = []
                for row in range(20):
                    medication_count = row % 4
                    records.append({
                        "patient_ref": f"SYNTHETIC-QUEUE-{index}-{uuid.uuid4().hex}",
                        "age_years": 40 + row,
                        "height_cm": 160 + (row % 5) * 4,
                        "weight_kg": 55 + row * 1.2,
                        "systolic_bp": 105 + row * 2,
                        "diastolic_bp": 65 + row,
                        "heart_rate_bpm": 60 + row * 2,
                        "medication_count": medication_count,
                        "medication_mg_total": medication_count * 50,
                        "label": row % 2,
                    })
                upload = httpx.post(
                    f"{services['m1'].url}/vitals/upload",
                    headers=bearer(spec["user_token"]),
                    json={"records": records},
                    timeout=30,
                )
                assert upload.status_code == 200, upload.text
                assert upload.json()["passed"] > 0, upload.json()

            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                if server.poll() is not None and server.returncode != 0:
                    raise RuntimeError(f"Flower server failed:\n{server_log_path.read_text()[-4000:]}")
                queue = httpx.get(
                    f"{services['m7'].url}/admin/retraining/requests",
                    headers=bearer(admin), timeout=20,
                )
                assert queue.status_code == 200, queue.text
                if len(queue.json()) == 2 and all(item["status"] == "COMPLETED" for item in queue.json()):
                    break
                if any(process.poll() not in (None, 0) for process in client_processes):
                    logs = "\n".join(
                        (pathlib.Path(tmp) / f"flower-client-{i}.log").read_text()[-3000:]
                        for i in (1, 2)
                    )
                    raise RuntimeError(f"A hospital Flower runner failed:\n{logs}")
                time.sleep(1)
            else:
                logs = server_log_path.read_text()[-4000:]
                raise RuntimeError(f"Timed out waiting for retraining completion:\n{logs}")

            server.wait(timeout=30)
            assert server.returncode == 0, server_log_path.read_text()[-4000:]
            run = type("RunOutput", (), {"stdout": server_log_path.read_text()})()
        finally:
            for process in client_processes:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
            for log in client_logs:
                log.close()
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
            server_log.close()

        def promoted_headers():
            sys.path.insert(0, str(ROOT / "module8-synthesis"))
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("fed_service_auth", ROOT / "module8-synthesis" / "service_auth.py")
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            finally:
                sys.path.remove(str(ROOT / "module8-synthesis"))
            return {"X-Service-Key": mod.mint_service_token("dev-only-signing-key-module8-to-module7", caller="module8",
                                                            audience=mod.AUD_PROMOTED_MODEL, hospital_id="*")}
        yield {"svc": services, "run": run, "tmp": tmp, "promoted_headers": promoted_headers,
               "admin": admin}
    finally:
        for s in services.values():
            s.stop()


def models_(fed):
    r = httpx.get(f"{fed['svc']['m7'].url}/admin/models", headers=bearer(fed["admin"]), timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def test_two_hospitals_trained_and_a_candidate_was_registered_but_not_deployed(fed):
    out = fed["run"].stdout
    assert "FINAL_ACCURACY:" in out
    rows = models_(fed)
    assert len(rows) == 1
    c = rows[0]
    assert c["deployment_status"] == "CANDIDATE" and c["validation_status"] == "PENDING"
    assert len(c["participating_hospitals"]) == 2
    cur = httpx.get(f"{fed['svc']['m7'].url}/admin/models/current",
                    params={"model_name": c["model_name"], "condition": c["condition"]},
                    headers=bearer(fed["admin"]), timeout=20)
    assert cur.status_code == 404      # nothing is in production just because training finished


def test_registry_row_contains_no_patient_level_data(fed):
    text = json.dumps(models_(fed)[0])
    for needle in ("UCI-CLE", "patient_ref", "age_years", "systolic_bp", "heart_rate_bpm"):
        assert needle not in text
    assert len(text) < 4000
    meta = models_(fed)[0]["training_metadata"]
    assert meta["differential_privacy"] is False and meta["secure_aggregation"] is False   # stated honestly


def test_candidate_hash_is_reported_without_exposing_candidate_weights(fed):
    c = models_(fed)[0]
    assert "parameters" not in c
    assert len(c["artifact_hash"]) == 64
    assert all(character in "0123456789abcdef" for character in c["artifact_hash"].lower())


def make_case_with_vitals(fed):
    m1 = fed["svc"]["m1"]
    sup = login(m1, "admin@fed.fedheal.local", ADMIN_PASSWORD)
    w = make_hospital_with_doctor(m1, sup)
    case = httpx.post(f"{m1.url}/cases", headers=bearer(w["doctor"]), timeout=30,
                      json={"patient_ref": "PAT-DEMO-FED", "admission_reason": "synthetic", "current_condition": "heart_disease"}).json()
    v = httpx.post(f"{m1.url}/cases/{case['id']}/vitals", headers=bearer(w["doctor"]), json={"record": VITALS}, timeout=30)
    assert v.status_code == 200, v.text
    return w["doctor"], case["id"]


def test_before_promotion_inference_refuses_instead_of_using_a_demo_model(fed):
    tok, cid = make_case_with_vitals(fed)
    fed["case"] = (tok, cid)
    r = httpx.post(f"{fed['svc']['m8'].url}/cases/{cid}/analyze", headers=bearer(tok), timeout=30)
    assert r.status_code == 503 and r.json()["detail"]["status"] == "MODEL_UNAVAILABLE"


def test_gate_passes_under_the_test_policy_and_a_super_admin_promotes(fed):
    m7, adm = fed["svc"]["m7"].url, bearer(fed["admin"])
    c = models_(fed)[0]
    v = httpx.post(f"{m7}/admin/models/{c['id']}/validate", headers=adm, timeout=20).json()
    names = {ch["name"]: ch["status"] for ch in v["validation_report"]["checks"]}
    assert set(names) == {"integrity", "participation", "data_quality", "minimum_metrics", "beats_majority_baseline",
                          "regression", "fairness"}
    assert names["integrity"] == "PASS" and names["participation"] == "PASS" and names["data_quality"] == "PASS"
    assert v["validation_status"] == "PASSED", v["validation_report"]
    p = httpx.post(f"{m7}/admin/models/{c['id']}/promote", json={}, headers=adm, timeout=20)
    assert p.status_code == 200 and p.json()["deployment_status"] == "DEPLOYED" and p.json()["approved_by"]
    print("\nmetrics (public UCI demo data, NOT clinical):", json.dumps(c["metrics"]))


def test_inference_serves_exactly_the_promoted_model_with_provenance(fed):
    tok, cid = fed["case"]
    reg = models_(fed)[0]
    r = httpx.post(f"{fed['svc']['m8'].url}/cases/{cid}/analyze", headers=bearer(tok), timeout=30)
    assert r.status_code == 200, r.text
    b = r.json()
    m = b["model"]
    assert m["federated"] is True and m["status"] == "DEPLOYED" and m["version"] == reg["version"]
    assert m["provenance"]["artifact_hash"] == reg["artifact_hash"] and m["provenance"]["registry_id"] == reg["id"]
    assert m["provenance"]["n_participating_hospitals"] == 2
    assert b["stub_or_fallback"] is False and b["clinician_review_required"] is True and b["non_clinical"] is True
    assert "DEMO" not in json.dumps(m)
    assert b["explanation"]["method"] == "linear_contributions"
    # the prediction is reproducible from the registry's weights (no hidden model)
    import numpy as np
    promoted = httpx.get(f"{fed['svc']['m7'].url}/admin/models/promoted", params={"condition": "heart_disease"},
                         headers=fed["promoted_headers"](), timeout=20).json()
    sys.path.insert(0, str(M3))
    try:
        import federation_registry as fr
    finally:
        sys.path.remove(str(M3))
    assert fr.artifact_hash([
        np.asarray(promoted["parameters"]["coef"], dtype=float),
        np.asarray(promoted["parameters"]["intercept"], dtype=float),
    ]) == reg["artifact_hash"]
    spec, coef = promoted["input_spec"], np.array(promoted["parameters"]["coef"][0])
    x = (np.array([VITALS[n] for n in spec["feature_names"]], float) - np.array(spec["center"])) / np.array(spec["scale"])
    z = float(coef @ x + promoted["parameters"]["intercept"][0])
    got = sum(c["contribution"] for c in b["explanation"]["contributions"]) + b["explanation"]["base_value"]
    assert abs(got - z) < 1e-9


def test_rollback_without_a_previous_model_is_refused(fed):
    c = models_(fed)[0]
    r = httpx.post(f"{fed['svc']['m7'].url}/admin/models/rollback",
                   params={"model_name": c["model_name"], "condition": c["condition"]},
                   headers=bearer(fed["admin"]), timeout=20)
    assert r.status_code == 409

"""
Two-hospital federated run against the real services, then the registry gate.

  Module 1 + Module 2 + Module 7 + Module 8 as real processes (throwaway SQLite)
    -> seed_uci_heart.py uploads public UCI Cleveland records for TWO hospitals
       through Module 1's front door (so they pass Module 2's validation)
    -> simulate_real.py: each hospital trains locally, FedAvg aggregates,
       the global model is scored on a pooled holdout, a CANDIDATE is registered
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
import subprocess
import sys
import tempfile

import httpx
import pytest

from test_doctor_workflow import VITALS, make_hospital_with_doctor
from test_e2e_flow import ADMIN_PASSWORD, ROOT, Service, base_env, bearer, free_port, login

M3 = ROOT / "module3-fedlearning"


@pytest.fixture(scope="module")
def fed():
    tmp = tempfile.mkdtemp(prefix="fedheal_fed_")
    p1, p2, p7, p8 = free_port(), free_port(), free_port(), free_port()
    m1_env = base_env(FEDHEAL_DATABASE_URL=f"sqlite:///{tmp}/auth.db", FEDHEAL_VALIDATION_API_URL=f"http://127.0.0.1:{p2}")
    subprocess.run([sys.executable, "-c", "import database, models; database.Base.metadata.create_all(bind=database.engine)"],
                   cwd=ROOT / "module1-auth", env=m1_env, check=True, timeout=60)
    subprocess.run([sys.executable, "create_super_admin.py", "--email", "admin@fed.fedheal.local"],
                   cwd=ROOT / "module1-auth", env={**m1_env, "FEDHEAL_BOOTSTRAP_ADMIN_PASSWORD": ADMIN_PASSWORD},
                   check=True, timeout=60, capture_output=True)
    services = {
        "m1": Service("module1", "module1-auth", p1, m1_env, tmp),
        "m2": Service("module2", "module2-validation", p2, base_env(FEDHEAL_ADMIN_API_URL=f"http://127.0.0.1:{p7}"), tmp),
        "m7": Service("module7", "module7-admin", p7,
                      base_env(FEDHEAL_ADMIN_DATABASE_URL=f"sqlite:///{tmp}/admin.db",
                               FEDHEAL_AUTH_API_URL=f"http://127.0.0.1:{p1}",
                               # TEST-ONLY relaxed gate (see module docstring)
                               FEDHEAL_GATE_MIN_ACCURACY="0.5", FEDHEAL_GATE_MIN_EVAL_EXAMPLES="30",
                               FEDHEAL_GATE_MAX_HOSPITAL_GAP="0.6", FEDHEAL_GATE_MIN_MARGIN_OVER_MAJORITY="0.0"), tmp),
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
        run = subprocess.run([sys.executable, "simulate_real.py"], cwd=M3, env=env,
                             capture_output=True, text=True, timeout=300)
        assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-1500:]
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
               "admin": login(services["m1"], "admin@fed.fedheal.local", ADMIN_PASSWORD)}
    finally:
        for s in services.values():
            s.stop()


def models_(fed):
    r = httpx.get(f"{fed['svc']['m7'].url}/admin/models", headers=bearer(fed["admin"]), timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def test_two_hospitals_trained_and_a_candidate_was_registered_but_not_deployed(fed):
    out = fed["run"].stdout
    assert "Registered candidate v1" in out and "NOT deployed" in out
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


def test_exported_weights_match_the_registered_hash(fed):
    import numpy as np
    sys.path.insert(0, str(M3))
    try:
        import federation_registry as fr
    finally:
        sys.path.remove(str(M3))
    c = models_(fed)[0]
    files = [f for f in os.listdir(f"{fed['tmp']}/artifacts") if f.endswith(".npz")]
    assert len(files) == 1
    assert fr.verify_artifact(os.path.join(fed["tmp"], "artifacts", files[0]), c["artifact_hash"])


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

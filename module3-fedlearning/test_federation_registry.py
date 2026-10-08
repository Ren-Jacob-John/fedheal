"""Candidate export + payload: hashing, integrity round-trip, derived (not asserted)
attestations, and proof that nothing patient-level can be in the payload.
Offline: uses the vendored public UCI Cleveland data, no services."""
import json

import numpy as np

import federation_registry as fr
import uci_heart
from client import HospitalClient
from data import train_test_split_per_hospital
from fedavg import federated_average
from model import build_model, get_model_parameters
from real_data import carve_global_holdout


class _Prov:
    def __init__(self, clean):
        self.is_clean = clean


def _run(n_hospitals=2, rounds=4):
    parts = uci_heart.load_partitions(n_hospitals=n_hospitals)
    parts, Xh, yh = carve_global_holdout(parts)
    splits = train_test_split_per_hospital(parts)
    clients = [HospitalClient(f"hospital-{i}", *s[0:1], s[2], s[1], s[3]) for i, s in enumerate(splits)]
    params = get_model_parameters(build_model())
    for _ in range(rounds):
        results = [c.fit(params, {}) for c in clients]
        params = federated_average([r[0] for r in results], [r[1] for r in results])
    return clients, params, Xh, yh, results


def test_client_fit_returns_only_weights_a_count_and_an_id():
    """Raw-data isolation at the federation boundary: everything a client hands
    back is weight arrays, an integer, and a tiny metrics dict."""
    clients, params, Xh, yh, results = _run()
    for new_params, n, metrics in results:
        assert all(isinstance(p, np.ndarray) and p.shape in ((1, 8), (1,)) for p in new_params)
        assert isinstance(n, int)
        assert set(metrics) == {"hospital_id"} and isinstance(metrics["hospital_id"], str)
        # no array in the payload has a row dimension anywhere near the local dataset
        assert all(p.size <= 8 for p in new_params)


def test_artifact_hash_is_stable_and_detects_tampering(tmp_path):
    _, params, *_ = _run()
    path, digest = fr.export_artifact(params, tmp_path)
    assert len(digest) == 64 and digest == fr.artifact_hash(params)
    assert fr.verify_artifact(path, digest)
    tampered = [params[0] + 1e-6, params[1]]
    assert fr.artifact_hash(tampered) != digest
    with np.load(path) as f:
        np.savez(path, coef=f["coef"] + 1e-6, intercept=f["intercept"])
    assert not fr.verify_artifact(path, digest)


def _payload(clean=True):
    clients, params, Xh, yh, _ = _run()
    per = {c.hospital_id: c.evaluate(params, {})[2]["accuracy"] for c in clients}
    model = build_model()
    model.coef_, model.intercept_ = params
    acc = model.score(Xh, yh)
    return fr.build_candidate_payload(
        condition="heart_disease", training_round=4, hospital_labels=[c.hospital_id for c in clients],
        global_accuracy=acc, n_eval=len(yh), per_hospital_accuracy=per, local_only_baseline=0.5,
        majority_class_floor=0.54, digest=fr.artifact_hash(params), provenances=[_Prov(clean)] * 2,
        data_source="uci_cleveland_public_demo")


def test_payload_is_aggregate_only():
    p = _payload()
    text = json.dumps(p)
    for forbidden in ("UCI-CLE", "patient_ref", "age_years", "systolic"):
        assert forbidden not in text
    # same key deny-list Module 7 enforces on the other side of the boundary
    deny = {"patient_ref", "patient_id", "records", "rows", "csv", "vitals", "history", "notes", "image",
            "scan", "features", "x", "y", "labels", "dataset", "email", "payload", "raw", "name"}

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield str(k).lower()
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    # hospital labels are VALUES under per_hospital_accuracy keys, which are labels not field names
    top = {k for k in keys({**p, "metrics": {k: v for k, v in p["metrics"].items() if k != "per_hospital_accuracy"}})}
    assert not (top & deny)
    assert set(p["metrics"]) >= {"accuracy", "n_eval", "per_hospital_accuracy"}
    assert p["metrics"]["n_eval"] > 0 and 0 <= p["metrics"]["accuracy"] <= 1
    assert len(text) < 2000                      # nothing dataset-sized can hide in here


def test_label_attestation_is_derived_and_privacy_gaps_are_stated_honestly():
    assert _payload(True)["training_metadata"]["labels_from_hospital_only"] is True
    assert _payload(False)["training_metadata"]["labels_from_hospital_only"] is False
    meta = _payload()["training_metadata"]
    assert meta["differential_privacy"] is False and meta["secure_aggregation"] is False
    assert meta["update_clipping"] is False and "none" in meta["transport_encryption"]


def test_register_returns_none_when_module7_is_down(monkeypatch):
    monkeypatch.setattr(fr, "ADMIN_API_URL", "http://127.0.0.1:9")
    assert fr.register_candidate(_payload(), timeout=1.0) is None

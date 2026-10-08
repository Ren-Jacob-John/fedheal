"""
Turns a finished federated run into a registry CANDIDATE for Module 7.

What leaves this process is deliberately tiny: hospital labels, counts,
aggregate accuracies, a hash of the model weights, and attestation flags
derived from the run itself. No records, no patient references, no
per-patient predictions, no local test sets. (Module 7 independently
refuses payloads containing such fields; see its assert_no_raw_data.)

Registering a candidate DEPLOYS NOTHING. Promotion is a separate, explicit,
super_admin-approved step after Module 7's validation gate.
"""
import hashlib
import os
from pathlib import Path

import httpx
import numpy as np

import config

ADMIN_API_URL = os.environ.get("FEDHEAL_ADMIN_API_URL", "http://localhost:8005")
MODEL_NAME = "vitals-fedavg-logreg"


def artifact_hash(params: list[np.ndarray]) -> str:
    """sha256 over a canonical byte form of the weights (dtype + shape + data),
    so the same weights always hash the same regardless of file container."""
    h = hashlib.sha256()
    for arr in params:
        a = np.ascontiguousarray(np.asarray(arr, dtype="<f8"))
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def export_artifact(params: list[np.ndarray], out_dir: str | os.PathLike) -> tuple[Path, str]:
    """Persist the global weights under MODEL_STORAGE_PATH-style out_dir; return (path, hash)."""
    digest = artifact_hash(params)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{MODEL_NAME}-{digest[:12]}.npz"
    np.savez(path, coef=params[0], intercept=params[1])
    return path, digest


def verify_artifact(path: str | os.PathLike, expected_hash: str) -> bool:
    with np.load(path) as f:
        return artifact_hash([f["coef"], f["intercept"]]) == expected_hash


def build_candidate_payload(*, condition: str, training_round: int, hospital_labels: list[str],
                            global_accuracy: float, n_eval: int, per_hospital_accuracy: dict[str, float],
                            local_only_baseline: float, majority_class_floor: float | None,
                            digest: str, provenances: list, data_source: str) -> dict:
    """Aggregate-only candidate description. Attestations are DERIVED, not asserted:
    labels_from_hospital_only is True only if no hospital's labels were placeholders."""
    clean = all(getattr(p, "is_clean", False) for p in provenances)
    return {
        "model_name": MODEL_NAME,
        "condition": condition,
        "training_round": int(training_round),
        "participating_hospitals": list(hospital_labels),
        "training_metadata": {
            "aggregation": "fedavg",
            "model_type": "sgd_logistic_regression",
            "n_hospitals": len(hospital_labels),
            "data_source": data_source,
            "validated_records_only": True,        # real_data.load_real_partitions drops flagged records
            "labels_from_hospital_only": bool(clean),
            "differential_privacy": False,
            "secure_aggregation": False,
            "update_clipping": False,
            "transport_encryption": "none (plaintext gRPC; development)",
        },
        "metrics": {
            "accuracy": float(global_accuracy),
            "n_eval": int(n_eval),
            "eval_set": "pooled global holdout carved before local training",
            "per_hospital_accuracy": {k: float(v) for k, v in per_hospital_accuracy.items()},
            "local_only_baseline_accuracy": float(local_only_baseline),
            **({"majority_class_floor": float(majority_class_floor)} if majority_class_floor is not None else {}),
        },
        "artifact_hash": digest,
    }


def register_candidate(payload: dict, *, timeout: float = 5.0) -> dict | None:
    """POST to Module 7 with the per-hop service key. Returns the stored row or None if unreachable."""
    key = config.get_secret("FEDHEAL_SVC_KEY_M3_M7", dev_default="dev-only-key-module3-to-module7")
    try:
        r = httpx.post(f"{ADMIN_API_URL}/admin/models/candidates", json=payload,
                       headers={"X-Service-Key": key}, timeout=timeout)
    except httpx.HTTPError:
        return None
    return r.json() if r.status_code == 201 else {"error": r.status_code, "detail": r.text[:300]}

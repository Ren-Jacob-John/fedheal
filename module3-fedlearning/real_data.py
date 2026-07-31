"""
Real-data loader — replaces data.py's synthetic partitions with each
hospital's own validated vitals, pulled from Module 1.

This is the "wire Module 2's validation output in as this module's
training data" item both this module's and Module 1's READMEs called out
as next-sprint work. Nothing in model.py or client.py needed to change:
they only ever consumed plain (X, y) numpy arrays, and that contract holds
here too.

Feature order matches data.py's FEATURE_NAMES count (N_FEATURES=8) so the
existing model architecture doesn't need to change either — the actual
column *meanings* are different (real vitals fields, not the synthetic
UCI-style features), which is fine since the model just sees floats.

    FEATURE_NAMES = [
        "age_years", "systolic_bp", "diastolic_bp", "heart_rate_bpm",
        "bmi (derived)", "weight_kg", "medication_count", "medication_mg_total",
    ]

Known gap, stated plainly rather than hidden: VitalsRecord (Module 1/2's
schema) has no real diagnosis/outcome field yet — hospitals haven't been
asked to supply one. Records DO carry an optional `label`, but until a
real clinical outcome is wired in, any record missing one gets a
rule-based PLACEHOLDER label (see `_placeholder_label` below) purely so
this loader is runnable end-to-end today. Swap `_placeholder_label` for a
real outcome field the moment hospitals have one to upload — do not treat
its output as a clinical signal.
"""
import os

import httpx
import numpy as np
from sklearn.model_selection import train_test_split

AUTH_API_URL = os.environ.get("FEDHEAL_AUTH_API_URL", "http://localhost:8001")
SERVICE_KEY = os.environ.get("FEDMED_SERVICE_KEY", "dev-only-internal-service-key")

FEATURE_KEYS = [
    "age_years", "systolic_bp", "diastolic_bp", "heart_rate_bpm",
    "weight_kg", "height_cm", "medication_count", "medication_mg_total",
]
N_FEATURES = len(FEATURE_KEYS)


def _placeholder_label(record: dict) -> int:
    """
    PLACEHOLDER ONLY — see module docstring. A simple, deterministic
    stand-in so the federated loop has *something* to learn from before
    real diagnosis labels exist: flags records with elevated systolic BP
    or a high medication load. This is not a diagnosis and must not be
    presented as one anywhere downstream.
    """
    systolic = record.get("systolic_bp") or 0
    return int(systolic >= 140 or (record.get("medication_mg_total") or 0) >= 300)


def _record_to_features(record: dict) -> np.ndarray:
    return np.array([float(record.get(k) or 0.0) for k in FEATURE_KEYS])


def list_active_hospitals() -> list[dict]:
    """Hospitals to potentially include in a real federated round."""
    resp = httpx.get(f"{AUTH_API_URL}/hospitals", timeout=10.0)
    resp.raise_for_status()
    return [h for h in resp.json() if h.get("is_active")]


def fetch_hospital_vitals(hospital_id: str, include_flagged: bool = False) -> list[dict]:
    """Pulls one hospital's validated vitals from Module 1's export endpoint."""
    resp = httpx.get(
        f"{AUTH_API_URL}/vitals/export",
        params={"hospital_id": hospital_id, "include_flagged": include_flagged},
        headers={"X-Service-Key": SERVICE_KEY},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def load_real_partitions(min_records_per_hospital: int = 10):
    """
    Returns (hospital_names, partitions) for every active hospital that has
    at least `min_records_per_hospital` validated vitals records — the same
    shape data.partition_for_hospitals() produces, so simulate_real.py can
    reuse simulate.py's train_test_split_per_hospital / FedAvg loop as-is.

    Hospitals below the threshold are skipped (reported, not silently
    dropped) rather than trained on too little data to mean anything.
    """
    hospital_names, partitions = [], []
    for hospital in list_active_hospitals():
        records = fetch_hospital_vitals(hospital["id"])
        if len(records) < min_records_per_hospital:
            print(f"  skipping {hospital['name']}: only {len(records)} validated records "
                  f"(need >= {min_records_per_hospital})")
            continue

        X = np.stack([_record_to_features(r) for r in records])
        y = np.array([
            r["label"] if r.get("label") is not None else _placeholder_label(r)
            for r in records
        ])
        hospital_names.append(hospital["name"])
        partitions.append((X, y))

    return hospital_names, partitions


def carve_global_holdout(partitions, test_size: float = 0.15, seed: int = 42):
    """
    Same role as data.load_full_dataset()'s holdout split, but applied
    per-hospital BEFORE the partitions are handed back for local
    train/test splitting — carving the holdout out of the pooled data
    afterward would let the same records end up both trained-on (as part
    of a hospital's local split) and in the "population no one trained on"
    holdout, which defeats the point of the comparison.

    Returns (remaining_partitions, X_global_holdout, y_global_holdout).
    """
    remaining = []
    holdout_X, holdout_y = [], []
    for X, y in partitions:
        if len(X) < 4:  # too small to carve anything off safely
            remaining.append((X, y))
            continue
        stratify = y if len(np.unique(y)) > 1 else None
        X_keep, X_hold, y_keep, y_hold = train_test_split(
            X, y, test_size=test_size, random_state=seed, stratify=stratify
        )
        remaining.append((X_keep, y_keep))
        holdout_X.append(X_hold)
        holdout_y.append(y_hold)

    X_global_holdout = np.concatenate(holdout_X) if holdout_X else np.empty((0, N_FEATURES))
    y_global_holdout = np.concatenate(holdout_y) if holdout_y else np.empty((0,))
    return remaining, X_global_holdout, y_global_holdout

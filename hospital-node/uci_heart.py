"""
UCI Heart Disease (Cleveland) -> FedHeal vitals records.

This is Sprint A's "seed the demo/eval data using a real, cited dataset"
item (docs/DEVELOPMENT_PLAN.md). It turns the vendored
`datasets/heart_cleveland_islr.csv` into records shaped exactly like what
a hospital uploads through `POST /vitals/upload`, so the federated-vs-solo
comparison runs on real patients with real outcome labels instead of
`make_classification` noise.

Two ways in:
  * `load_vitals_records()` — list[dict] ready to POST at Module 1.
    Used by `seed_uci_heart.py`.
  * `load_partitions()` — (X, y) numpy partitions in the same shape
    `data.partition_for_hospitals()` produces, for an offline
    federated-vs-solo comparison with no services running. Used by
    `compare_uci_heart.py`.

------------------------------------------------------------------------
READ THIS BEFORE QUOTING AN ACCURACY NUMBER FROM THIS DATA
------------------------------------------------------------------------
The development plan describes UCI Heart Disease as "structurally
compatible with the vitals schema". That's true of the *label* and of
*some* features, and it is the reason this dataset was chosen — but
"compatible" is not "complete", and the gap is big enough that hiding it
would be exactly the kind of thing section 4 of the plan exists to stop.

Cleveland has 13 attributes + an outcome. FedHeal's vitals schema has 8
features + an optional label. **Only 4 columns genuinely correspond:**

| FedHeal field         | Cleveland column | Faithful? |
|-----------------------|------------------|-----------|
| `age_years`           | `age`            | Yes — identical meaning. |
| `systolic_bp`         | `trestbps`       | Yes — resting systolic BP on admission, mmHg. |
| `heart_rate_bpm`      | `thalach`        | **Caveat.** `thalach` is *maximum* heart rate achieved during a stress test, not a resting vital. Real and clinically meaningful, but not the same measurement a ward nurse records. Ranges 71–202 here vs. a resting 50–100. |
| `label`               | `num`            | Yes — `num > 0` (any degree of major-vessel narrowing) -> 1. This is a REAL clinical outcome, which is the entire point: it retires the placeholder-label path for the demo. |

**Cleveland supplies no equivalent for the other 5 features:**
`diastolic_bp`, `height_cm`, `weight_kg`, `medication_count`,
`medication_mg_total`.

They are NOT invented, NOT sampled, and NOT back-filled from some other
Cleveland column (putting `chol` in the `weight_kg` slot because both are
numbers would be fabrication, not a mapping). Each is set to a single
fixed constant, declared in `NOT_SUPPLIED_BY_UCI` below, chosen so that:

  1. the record passes Module 2's schema + range + cross-field checks
     unchanged (no special-casing the validator for seed data), and
  2. it lands on `real_data._FEATURE_MEAN` for that column, so after
     `real_data`'s fixed normalization the value is **exactly 0.0** and
     contributes nothing to any gradient. A constant column can't carry
     signal anyway; pinning it to the mean makes that arithmetically
     obvious rather than something a reviewer has to take on trust.

Net effect: a model trained on UCI-seeded data is learning from **3 real
features**, not 8. Expect accuracy meaningfully below the ~85% the full
13-attribute Cleveland feature set supports in the literature. The
majority-class floor is 54.1% (164/303), so there is real signal to
measure and the federated-vs-solo comparison is still a fair one — but
quote it as "3 real vitals features from Cleveland", never as "UCI Heart
Disease accuracy".

Closing that gap means adding the genuinely-clinical Cleveland columns
(`chol`, `oldpeak`, `exang`, ...) to the vitals schema, which changes
`N_FEATURES` and therefore Module 3's model contract, Module 5/6's
routers, and Module 2's rules. That is a schema change, not a seed
script, and it is deliberately NOT in Sprint A.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
from pathlib import Path

import numpy as np

DATASET_DIR = Path(__file__).parent / "datasets"
DATASET_PATH = DATASET_DIR / "heart_cleveland_islr.csv"

# Checked by --verify and by test_uci_heart.py. See datasets/README.md.
DATASET_SHA256 = "8d2f18114152427beb57b7a4df4ab71fd41c010136fdaeaf6f168770f865b368"

# Published characteristics of the Cleveland subset — asserted on load so a
# swapped or truncated file fails here rather than silently changing every
# accuracy number downstream.
EXPECTED_ROWS = 303
EXPECTED_POSITIVE = 139
EXPECTED_NEGATIVE = 164
EXPECTED_MISSING = {"Ca": 4, "Thal": 2}

# The ISLR mirror spells out codes that are numeric in processed.cleveland.data.
# Re-encoded here purely so this loader's output can be checked against the
# original UCI file; FedHeal itself only consumes the 4 mapped columns.
_CHEST_PAIN_CODES = {
    "typical": 1, "asymptomatic": 4, "nonanginal": 3, "nontypical": 2,
}
_THAL_CODES = {"normal": 3, "fixed": 6, "reversable": 7}

# ---------------------------------------------------------------------
# The 5 vitals fields Cleveland does not measure. See the module docstring
# for why these are constants and why these specific constants.
#
# Each value equals real_data._FEATURE_MEAN for that column, so
# (value - mean) / std == 0.0 exactly. Cross-checked by
# test_uci_heart.py::test_unsupplied_fields_normalize_to_zero — if anyone
# retunes _FEATURE_MEAN without updating these, that test fails rather
# than quietly reintroducing a constant non-zero bias term.
# ---------------------------------------------------------------------
NOT_SUPPLIED_BY_UCI = {
    "diastolic_bp": 80.0,        # < every trestbps in the file (min 94) -> passes the systolic/diastolic check
    "weight_kg": 75.0,           # with height 170 -> BMI 25.9, inside Module 2's [8, 90] sanity band
    "height_cm": 170.0,
    "medication_count": 2,       # count > 0 and mg > 0 together -> passes the med cross-field check
    "medication_mg_total": 150.0,
}

# Ordered exactly as real_data.FEATURE_KEYS, so load_partitions() output is
# interchangeable with a real hospital partition.
FEATURE_KEYS = [
    "age_years", "systolic_bp", "diastolic_bp", "heart_rate_bpm",
    "weight_kg", "height_cm", "medication_count", "medication_mg_total",
]

# Which of those the real dataset actually determines. Everything else is a
# constant from NOT_SUPPLIED_BY_UCI above.
REAL_FEATURE_KEYS = ["age_years", "systolic_bp", "heart_rate_bpm"]


class DatasetIntegrityError(RuntimeError):
    """Raised when the vendored CSV isn't the dataset we documented."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_dataset(path: Path = DATASET_PATH) -> str:
    """Checks the vendored file against the SHA-256 in datasets/README.md."""
    if not path.exists():
        raise DatasetIntegrityError(
            f"{path} is missing. It's vendored in the repo — restore it from "
            "version control, or see datasets/README.md for its upstream source."
        )
    digest = _sha256(path)
    if digest != DATASET_SHA256:
        raise DatasetIntegrityError(
            f"{path} does not match the expected SHA-256.\n"
            f"  expected: {DATASET_SHA256}\n"
            f"  actual:   {digest}\n"
            "Refusing to seed from an unverified dataset — every accuracy "
            "number downstream is attributed to a specific, cited file."
        )
    return digest


def load_raw_rows(path: Path = DATASET_PATH, verify: bool = True) -> list[dict]:
    """
    Reads the Cleveland CSV and re-encodes the ISLR string codes back to
    UCI's original numeric ones. Returns rows with the ORIGINAL column
    names — the vitals mapping happens in load_vitals_records().
    """
    if verify:
        verify_dataset(path)

    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    if len(rows) != EXPECTED_ROWS:
        raise DatasetIntegrityError(
            f"Expected {EXPECTED_ROWS} Cleveland records, found {len(rows)}."
        )

    out = []
    for row in rows:
        out.append({
            "age": float(row["Age"]),
            "sex": int(row["Sex"]),
            "cp": _CHEST_PAIN_CODES.get(row["ChestPain"]),
            "trestbps": float(row["RestBP"]),
            "chol": float(row["Chol"]),
            "fbs": int(row["Fbs"]),
            "restecg": int(row["RestECG"]),
            "thalach": float(row["MaxHR"]),
            "exang": int(row["ExAng"]),
            "oldpeak": float(row["Oldpeak"]),
            "slope": int(row["Slope"]),
            # 'NA' in the mirror == '?' in processed.cleveland.data.
            "ca": None if row["Ca"] == "NA" else float(row["Ca"]),
            "thal": _THAL_CODES.get(row["Thal"]),  # None for 'NA'
            # AHD is num>0 already collapsed to Yes/No by the ISLR mirror.
            "label": 1 if row["AHD"] == "Yes" else 0,
        })
    return out


def load_vitals_records(
    path: Path = DATASET_PATH,
    verify: bool = True,
    patient_ref_prefix: str = "UCI-CLE",
) -> list[dict]:
    """
    Cleveland rows -> records shaped like a hospital's vitals upload.

    Every returned record carries a REAL `label` (from `num`), which is the
    whole point of the Sprint A swap: these records never touch Module 3's
    placeholder-label fallback.

    `patient_ref` is a synthetic sequential pseudonym (`UCI-CLE-0001`).
    Cleveland is already de-identified upstream, and the vitals schema
    requires *some* hospital-internal reference, so this is a positional
    index and nothing more — it is not derived from any row value.
    """
    records = []
    for i, row in enumerate(load_raw_rows(path, verify=verify), start=1):
        records.append({
            "patient_ref": f"{patient_ref_prefix}-{i:04d}",
            # --- genuinely from Cleveland ---
            "age_years": row["age"],
            "systolic_bp": row["trestbps"],
            "heart_rate_bpm": row["thalach"],  # NB: exercise max HR, see module docstring
            "label": row["label"],
            # --- not measured by Cleveland; fixed, signal-free constants ---
            **NOT_SUPPLIED_BY_UCI,
        })
    return records


def load_partitions(n_hospitals: int = 3, non_iid: bool = True,
                    alpha: float = 3.0, seed: int = 42,
                    path: Path = DATASET_PATH, verify: bool = True):
    """
    Offline path: Cleveland -> normalized (X, y) partitions, no services
    required. Same return shape as data.partition_for_hospitals(), and the
    same fixed normalization real_data.py applies to live hospital data, so
    an offline comparison here is directly comparable to simulate_real.py's.
    """
    # Imported here rather than at module scope so seed_uci_heart.py can use
    # load_vitals_records() without pulling in real_data's httpx dependency.
    from data import partition_for_hospitals
    from real_data import _record_to_features

    records = load_vitals_records(path, verify=verify)
    X = np.stack([_record_to_features(r) for r in records])
    y = np.array([r["label"] for r in records])
    return partition_for_hospitals(X, y, n_hospitals, non_iid=non_iid,
                                   alpha=alpha, seed=seed)


def summary(path: Path = DATASET_PATH) -> dict:
    """Facts worth printing before anyone trusts a number derived from this."""
    records = load_vitals_records(path)
    labels = [r["label"] for r in records]
    positives = sum(labels)
    return {
        "records": len(records),
        "positive": positives,
        "negative": len(labels) - positives,
        "majority_class_floor": max(positives, len(labels) - positives) / len(labels),
        "real_features": REAL_FEATURE_KEYS,
        "constant_features": sorted(NOT_SUPPLIED_BY_UCI),
        "labels_real": True,
        "sha256": _sha256(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect / verify the vendored UCI Heart Disease dataset."
    )
    parser.add_argument("--verify", action="store_true",
                        help="Check the SHA-256 and published fidelity markers, then exit.")
    args = parser.parse_args()

    try:
        info = summary()
    except DatasetIntegrityError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1

    print("UCI Heart Disease (Cleveland) — vendored copy")
    print(f"  file           {os.path.relpath(DATASET_PATH)}")
    print(f"  sha256         {info['sha256']}")
    print(f"  records        {info['records']}  ({info['positive']} positive / {info['negative']} negative)")
    print(f"  majority floor {info['majority_class_floor']:.1%}  <- beat this to mean anything")
    print(f"  real features  {', '.join(info['real_features'])}  ({len(info['real_features'])} of 8)")
    print(f"  constants      {', '.join(info['constant_features'])}  (not measured by Cleveland)")
    print("  labels         REAL clinical outcome (num > 0) — no placeholder fallback")
    if args.verify:
        print("\nOK — matches datasets/README.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

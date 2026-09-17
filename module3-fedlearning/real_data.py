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

LABELS (changed in Sprint A — read this if you remember the old behaviour)
-------------------------------------------------------------------------
This loader used to silently substitute a rule-based PLACEHOLDER label for
any record that arrived without one. That made the *default* end-to-end
path a model trained partly on labels no clinician ever produced, with
nothing in the output saying so.

That is now inverted:

  * `GET /vitals/export` defaults to `labeled_only=true`, so unlabeled
    records don't reach this module at all unless explicitly requested.
  * `_placeholder_label()` is only reachable via an explicit
    `allow_placeholder_labels=True` argument (surfaced as
    `--allow-placeholder-labels` on simulate_real.py and client_runner.py).
  * Without that flag, hitting an unlabeled record raises
    `UnlabeledDataError` and names the hospital. Loudly failing beats
    quietly fabricating.
  * With the flag, every loader returns a `LabelProvenance` alongside the
    data, logs a warning banner, and callers stamp the round's admin
    report so a placeholder-contaminated accuracy number can never be
    mistaken later for a real one.

Hospitals that genuinely have outcomes should be marked `requires_label`
in Module 1, which makes Module 2 reject their unlabeled uploads outright
(rules.check_required_label) — the problem gets caught at upload time, by
the person who can fix the export, instead of at training time.
"""
import logging
from dataclasses import dataclass, field
import os

import httpx
import numpy as np
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)

AUTH_API_URL = os.environ.get("FEDHEAL_AUTH_API_URL", "http://localhost:8001")
SERVICE_KEY = os.environ.get("FEDHEAL_SVC_KEY_M3_M1", "iamgodofthunder")
FEATURE_KEYS = [
    "age_years", "systolic_bp", "diastolic_bp", "heart_rate_bpm",
    "weight_kg", "height_cm", "medication_count", "medication_mg_total",
]
N_FEATURES = len(FEATURE_KEYS)

# Fixed normalization constants — deliberately NOT fit from any hospital's
# own data. Every hospital has to apply the EXACT same transform to the
# EXACT same feature, or FedAvg silently breaks: it's averaging models
# that were each trained in a different feature space. A per-hospital
# StandardScaler wouldn't leak anything sensitive on its own, but it
# would violate that assumption just as badly as skipping scaling
# entirely — so these are fixed, clinically-plausible general-population
# reference values agreed on in advance, not statistics computed from
# this project's own demo data (which would silently drift as demo data
# changes).
#
# Why this matters at all: verified directly while investigating why
# test_client_runner_matches_simulation.py's real-vs-reproduction
# comparison wasn't reproducible — these columns span roughly 0-5
# (medication_count) to 0-400+ (medication_mg_total) UNSCALED, and
# SGDClassifier's gradient step scales with raw feature magnitude. A
# single partial_fit() epoch on unscaled data sent coef_ from 0 to the
# thousands; see docs/development-plan-to-oct20.md's "next sprint"
# section for the full trace. That's not an FL-networking bug — it
# reproduces identically in simulate_real.py, which never touches the
# network — but it does mean every real-data FL path was numerically
# unstable (wildly different round-to-round accuracy, hypersensitive to
# floating-point summation order) until this fix.
_FEATURE_MEAN = np.array([50.0, 120.0, 80.0, 75.0, 75.0, 170.0, 2.0, 150.0])
_FEATURE_STD = np.array([20.0, 20.0, 10.0, 12.0, 18.0, 12.0, 2.0, 120.0])


class UnlabeledDataError(ValueError):
    """
    Raised when a hospital's export contains records with no real outcome
    label and the caller hasn't explicitly opted into placeholder labels.

    Its own exception type (not a bare ValueError) so callers can catch
    exactly this and print the fix, rather than lumping it in with
    "not enough records" and every other ValueError this module raises.
    """


@dataclass
class LabelProvenance:
    """
    Where a partition's labels came from. Returned alongside (X, y) so a
    caller can never hold the data without also holding the answer to
    "is any of this made up?".
    """
    hospital: str
    total: int = 0
    real: int = 0
    placeholder: int = 0
    _hospitals: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return self.placeholder == 0

    def banner(self) -> str:
        if self.is_clean:
            return (f"labels: {self.real}/{self.total} real clinical outcomes "
                    f"({self.hospital}) — no placeholders")
        pct = self.placeholder / self.total if self.total else 0
        return (
            f"!! PLACEHOLDER LABELS IN USE ({self.hospital}): "
            f"{self.placeholder}/{self.total} ({pct:.0%}) of labels are rule-based "
            f"stand-ins, NOT clinical outcomes. Any accuracy number derived from "
            f"this run is not a clinical result."
        )


def _placeholder_label(record: dict) -> int:
    """
    PLACEHOLDER ONLY — see module docstring. A simple, deterministic
    stand-in so the federated loop has *something* to learn from before
    real diagnosis labels exist: flags records with elevated systolic BP
    or a high medication load. This is not a diagnosis and must not be
    presented as one anywhere downstream.

    As of Sprint A this is unreachable unless a caller explicitly passes
    allow_placeholder_labels=True. Kept rather than deleted because a
    hospital onboarding without outcomes yet is a real situation — it just
    isn't the default one any more.
    """
    systolic = record.get("systolic_bp") or 0
    return int(systolic >= 140 or (record.get("medication_mg_total") or 0) >= 300)


def _labels_for(records: list[dict], hospital: str,
                allow_placeholder_labels: bool) -> tuple[np.ndarray, LabelProvenance]:
    """
    Turns records into a y vector, and refuses to invent anything unless
    told to. Single implementation shared by both loaders below, so the
    per-hospital client path and the pooled simulation path can't drift
    into different label policies.
    """
    prov = LabelProvenance(hospital=hospital, total=len(records))
    unlabeled = [r for r in records if r.get("label") is None]

    if unlabeled and not allow_placeholder_labels:
        raise UnlabeledDataError(
            f"{hospital}: {len(unlabeled)} of {len(records)} validated records have "
            f"no clinical outcome label.\n"
            f"  Fix (preferred): upload the real outcomes. Mark this hospital "
            f"requires_label=true in Module 1 so unlabeled uploads are rejected "
            f"at the door instead of reaching training.\n"
            f"  Override (demo only): pass --allow-placeholder-labels to train on "
            f"rule-based stand-in labels. The run will be flagged as "
            f"non-clinical everywhere it's reported."
        )

    y = []
    for r in records:
        if r.get("label") is not None:
            y.append(int(r["label"]))
            prov.real += 1
        else:
            y.append(_placeholder_label(r))
            prov.placeholder += 1

    if prov.placeholder:
        logger.warning(prov.banner())

    return np.array(y), prov


def _record_to_features(record: dict) -> np.ndarray:
    raw = np.array([float(record.get(k) or 0.0) for k in FEATURE_KEYS])
    return (raw - _FEATURE_MEAN) / _FEATURE_STD


def list_active_hospitals() -> list[dict]:
    """Hospitals to potentially include in a real federated round."""
    resp = httpx.get(f"{AUTH_API_URL}/hospitals", timeout=10.0)
    resp.raise_for_status()
    return [h for h in resp.json() if h.get("is_active")]


def fetch_hospital_vitals(hospital_id: str, include_flagged: bool = False,
                          labeled_only: bool = True) -> list[dict]:
    """
    Pulls one hospital's validated vitals from Module 1's export endpoint.

    `labeled_only=True` (the Sprint A default) asks Module 1 to filter out
    records with no real outcome server-side, so unlabeled data never even
    crosses the wire into this module. Callers that have opted into
    placeholder labels pass False.
    """
    resp = httpx.get(
        f"{AUTH_API_URL}/vitals/export",
        params={
            "hospital_id": hospital_id,
            "include_flagged": include_flagged,
            "labeled_only": labeled_only,
        },
        headers={"X-Service-Key": SERVICE_KEY},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def resolve_hospital_id(hospital_name: str) -> str:
    """
    Convenience for client_runner.py's --hospital-name flag: hospitals are
    keyed by DB id (a UUID) everywhere real, but an operator starting a
    client by hand shouldn't have to go paste that id out of a database —
    look it up by the hospital's display name instead.
    """
    resp = httpx.get(f"{AUTH_API_URL}/hospitals", timeout=10.0)
    resp.raise_for_status()
    matches = [h for h in resp.json() if h["name"] == hospital_name]
    if not matches:
        raise ValueError(f"No hospital named {hospital_name!r} found at {AUTH_API_URL}/hospitals")
    return matches[0]["id"]


def load_single_hospital_partition(
    hospital_id: str, min_records: int = 10, include_flagged: bool = False,
    allow_placeholder_labels: bool = False,
):
    """
    Same per-record -> (X, y) conversion as load_real_partitions() below, but
    scoped to exactly one hospital and meant to be called FROM that
    hospital's own client_runner.py process — unlike load_real_partitions(),
    which pulls every active hospital's data into one place (fine for
    simulate_real.py's in-process stand-in, wrong for a real client, which
    should only ever touch its own hospital's data).

    Raises ValueError (not silently returning empty arrays) if this hospital
    doesn't have enough validated data yet, so client_runner.py fails loudly
    instead of "federating" on nothing.

    Returns (X, y, provenance). The third element is new in Sprint A — the
    signature change is deliberate rather than making it optional, so every
    call site has to acknowledge label provenance instead of inheriting a
    silent default.
    """
    records = fetch_hospital_vitals(
        hospital_id,
        include_flagged=include_flagged,
        labeled_only=not allow_placeholder_labels,
    )
    if len(records) < min_records:
        raise ValueError(
            f"hospital {hospital_id} has only {len(records)} validated, "
            f"{'labeled ' if not allow_placeholder_labels else ''}vitals "
            f"records (need >= {min_records}). Upload more via the dashboard "
            f"before running client_runner.py for this hospital."
            + ("" if allow_placeholder_labels else
               "\n  If this hospital has records but no outcome labels, that's "
               "the cause — check GET /training-status, which now reports "
               "labeled_records separately.")
        )

    X = np.stack([_record_to_features(r) for r in records])
    y, provenance = _labels_for(records, hospital_id, allow_placeholder_labels)
    return X, y, provenance


def load_real_partitions(min_records_per_hospital: int = 10,
                         allow_placeholder_labels: bool = False):
    """
    Returns (hospital_names, partitions) for every active hospital that has
    at least `min_records_per_hospital` validated vitals records — the same
    shape data.partition_for_hospitals() produces, so simulate_real.py can
    reuse simulate.py's train_test_split_per_hospital / FedAvg loop as-is.

    Hospitals below the threshold are skipped (reported, not silently
    dropped) rather than trained on too little data to mean anything.

    Returns (hospital_names, partitions, provenance) — the third element is
    new in Sprint A; see `_labels_for`. Provenance is per-hospital, because
    "2 of 4 hospitals are running on placeholder labels" is a materially
    different situation from "all 4 are", and a single pooled flag would
    lose that.
    """
    hospital_names, partitions, provenances = [], [], []
    for hospital in list_active_hospitals():
        records = fetch_hospital_vitals(
            hospital["id"], labeled_only=not allow_placeholder_labels
        )
        if len(records) < min_records_per_hospital:
            suffix = "" if allow_placeholder_labels else " with outcome labels"
            print(f"  skipping {hospital['name']}: only {len(records)} validated records"
                  f"{suffix} (need >= {min_records_per_hospital})")
            continue

        X = np.stack([_record_to_features(r) for r in records])
        y, provenance = _labels_for(records, hospital["name"], allow_placeholder_labels)
        hospital_names.append(hospital["name"])
        partitions.append((X, y))
        provenances.append(provenance)

    return hospital_names, partitions, provenances


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
        # Same fix as client_runner.py/data.py: a class needs >= 2 members
        # to stratify on, not just "more than one distinct class" — a real
        # hospital partition can have exactly one record of a class.
        classes, counts = np.unique(y, return_counts=True)
        stratify = y if len(classes) > 1 and counts.min() >= 2 else None
        X_keep, X_hold, y_keep, y_hold = train_test_split(
            X, y, test_size=test_size, random_state=seed, stratify=stratify
        )
        remaining.append((X_keep, y_keep))
        holdout_X.append(X_hold)
        holdout_y.append(y_hold)

    X_global_holdout = np.concatenate(holdout_X) if holdout_X else np.empty((0, N_FEATURES))
    y_global_holdout = np.concatenate(holdout_y) if holdout_y else np.empty((0,))
    return remaining, X_global_holdout, y_global_holdout

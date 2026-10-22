"""
Entities this service owns, stored in Firestore (one collection each — see
COLLECTION). Previously SQLAlchemy tables; now plain dataclasses so attribute
access and pydantic `from_attributes` responses are unchanged. Mapping to
Firestore documents is docstore.to_doc / from_doc; all reads and writes go
through repo.py.

`blob_field` columns hold arbitrary JSON and are stored as JSON text: model
weights are a list of lists, and Firestore rejects nested arrays.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from docstore import blob_field


def gen_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(kw_only=True)
class TrainingRound:
    """
    One document per completed federated round, reported by Module 3 (simulate.py
    or the real server.py) after it finishes averaging. This is what lets
    the operator "monitor global model performance across rounds" without
    tailing console logs.
    """
    COLLECTION = "training_rounds"

    id: str = field(default_factory=gen_uuid)
    round_number: int
    n_hospitals: int
    global_accuracy: Optional[float] = None
    baseline_accuracy: Optional[float] = None  # local-only baseline, for comparison
    notes: Optional[str] = None
    reported_at: datetime = field(default_factory=utcnow)


@dataclass(kw_only=True)
class RetrainingRequest:
    """Count-only, hospital-scoped request for a runner to join a Flower round."""
    COLLECTION = "retraining_requests"

    id: str
    hospital_id: str
    eligible_records: int
    threshold_bucket: int
    baseline_records: int
    status: str = "PENDING"  # PENDING|CLAIMED|COMPLETED|FAILED
    candidate_id: Optional[str] = None
    created_at: datetime = field(default_factory=utcnow)
    claimed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass(kw_only=True)
class RetrainingProgress:
    """Per-hospital count baseline; contains no record-level data."""
    COLLECTION = "retraining_progress"

    hospital_id: str
    last_completed_records: int
    latest_eligible_records: int
    updated_at: datetime = field(default_factory=utcnow)


@dataclass(kw_only=True)
class ValidationFlag:
    """
    A SUMMARY of something Module 2 rejected or flagged for a hospital's
    batch upload — counts and reasons only, never the underlying record.
    This is the "view validation-layer flags across hospitals without
    seeing their raw data" requirement made concrete: this collection cannot
    contain patient data because Module 2 never sends it any.
    """
    COLLECTION = "validation_flags"

    id: str = field(default_factory=gen_uuid)
    hospital_id: str
    status: str  # "flagged" or "rejected"
    reason: str
    count: int = 1
    reported_at: datetime = field(default_factory=utcnow)


@dataclass(kw_only=True)
class ModelVersion:
    """
    Model registry (P0). One document per candidate/deployed global model version.

    Lifecycle:  CANDIDATE -> (validate) -> VALIDATED | REJECTED
                VALIDATED -> (promote, super_admin) -> DEPLOYED
                DEPLOYED  -> (new promotion) -> RETIRED
                DEPLOYED  -> (rollback) -> ROLLED_BACK, previous RETIRED -> DEPLOYED
    A model is NEVER DEPLOYED merely because training finished.

    Only metadata lives here: ids, hashes, aggregate metrics. No patient data.
    `metrics` are reported by the training side (Module 3) from its own
    held-out evaluation; the registry stores and gates them, it does not
    re-measure them.
    """
    COLLECTION = "model_versions"

    id: str = field(default_factory=gen_uuid)
    model_name: str
    version: str
    parent_version: Optional[str] = None
    condition: str
    training_round: int
    participating_hospitals: list = field(default_factory=list)
    training_metadata: dict = blob_field(default_factory=dict)
    metrics: dict = blob_field(default_factory=dict)
    validation_status: str = "PENDING"   # PENDING|PASSED|FAILED
    validation_report: Optional[dict] = blob_field(default=None)
    deployment_status: str = "CANDIDATE"
    replaces_id: Optional[str] = None    # the model this one displaced on promotion
    artifact_hash: str
    # Weights + the input transform needed to serve this model. Verified against artifact_hash at registration.
    parameters: Optional[dict] = blob_field(default=None)
    input_spec: Optional[dict] = blob_field(default=None)
    created_at: datetime = field(default_factory=utcnow)
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None

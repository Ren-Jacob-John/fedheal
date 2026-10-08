import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, DateTime, JSON

from database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TrainingRound(Base):
    """
    One row per completed federated round, reported by Module 3 (simulate.py
    or the real server.py) after it finishes averaging. This is what lets
    the operator "monitor global model performance across rounds" without
    tailing console logs.
    """
    __tablename__ = "training_rounds"

    id = Column(String, primary_key=True, default=gen_uuid)
    round_number = Column(Integer, nullable=False)
    n_hospitals = Column(Integer, nullable=False)
    global_accuracy = Column(Float, nullable=True)
    baseline_accuracy = Column(Float, nullable=True)  # local-only baseline, for comparison
    notes = Column(String, nullable=True)
    reported_at = Column(DateTime, default=utcnow)


class ValidationFlag(Base):
    """
    A SUMMARY of something Module 2 rejected or flagged for a hospital's
    batch upload — counts and reasons only, never the underlying record.
    This is the "view validation-layer flags across hospitals without
    seeing their raw data" requirement made concrete: this table cannot
    contain patient data because Module 2 never sends it any.
    """
    __tablename__ = "validation_flags"

    id = Column(String, primary_key=True, default=gen_uuid)
    hospital_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False)  # "flagged" or "rejected"
    reason = Column(String, nullable=False)
    count = Column(Integer, nullable=False, default=1)
    reported_at = Column(DateTime, default=utcnow)


class ModelVersion(Base):
    """
    Model registry (P0). One row per candidate/deployed global model version.

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
    __tablename__ = "model_versions"

    id = Column(String, primary_key=True, default=gen_uuid)
    model_name = Column(String, nullable=False, index=True)
    version = Column(String, nullable=False)
    parent_version = Column(String, nullable=True)
    condition = Column(String, nullable=False, index=True)
    training_round = Column(Integer, nullable=False, index=True)
    participating_hospitals = Column(JSON, nullable=False, default=list)
    training_metadata = Column(JSON, nullable=False, default=dict)
    metrics = Column(JSON, nullable=False, default=dict)
    validation_status = Column(String, nullable=False, default="PENDING")   # PENDING|PASSED|FAILED
    validation_report = Column(JSON, nullable=True)
    deployment_status = Column(String, nullable=False, default="CANDIDATE", index=True)
    replaces_id = Column(String, nullable=True)       # the model this one displaced on promotion
    artifact_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow, index=True)
    approved_at = Column(DateTime, nullable=True)
    approved_by = Column(String, nullable=True)

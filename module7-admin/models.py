import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, DateTime

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

from datetime import datetime

from pydantic import BaseModel


class HospitalStatusUpdate(BaseModel):
    is_active: bool


class TrainingRoundIn(BaseModel):
    round_number: int
    n_hospitals: int
    global_accuracy: float | None = None
    baseline_accuracy: float | None = None
    notes: str | None = None


class TrainingRoundOut(TrainingRoundIn):
    id: str
    reported_at: datetime

    class Config:
        from_attributes = True


class ValidationFlagIn(BaseModel):
    hospital_id: str
    status: str  # "flagged" or "rejected"
    reason: str
    count: int = 1


class ValidationFlagOut(ValidationFlagIn):
    id: str
    reported_at: datetime

    class Config:
        from_attributes = True


class OverviewOut(BaseModel):
    total_hospitals: int
    active_hospitals: int
    inactive_hospitals: int
    latest_round_number: int | None
    latest_global_accuracy: float | None
    total_rounds_recorded: int
    total_flags: int
    flags_last_7_days: int

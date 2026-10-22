from datetime import datetime

from pydantic import BaseModel, Field


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


class RetrainingEligibilityIn(BaseModel):
    eligible_records: int = Field(ge=0)


class RetrainingRequestOut(BaseModel):
    id: str
    hospital_id: str
    eligible_records: int
    threshold_bucket: int
    baseline_records: int
    status: str
    candidate_id: str | None = None
    created_at: datetime
    claimed_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class RetrainingCandidateStatusOut(BaseModel):
    registered: bool
    candidate_id: str | None = None
    version: str | None = None
    deployment_status: str | None = None


class RetrainingCompletionIn(BaseModel):
    request_id: str
    status: str = Field(pattern="^(COMPLETED|FAILED)$")
    eligible_records: int | None = Field(default=None, ge=0)


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

"""
The shape of a single "vitals" record a hospital uploads for the structured-data
track. Deliberately excludes anything identifying — see rules.FORBIDDEN_FIELDS
for the de-identification check that runs before this schema is even parsed.
"""
from typing import Optional

from pydantic import BaseModel, Field


class VitalsRecord(BaseModel):
    # patient_ref is a hospital-internal pseudonymous ID (e.g. "P-00231"),
    # never a real name/MRN. It never leaves this service.
    patient_ref: str = Field(..., max_length=64)

    age_years: float = Field(..., ge=0, le=130)
    height_cm: float = Field(..., gt=0)
    weight_kg: float = Field(..., gt=0)
    systolic_bp: Optional[float] = None
    diastolic_bp: Optional[float] = None
    heart_rate_bpm: Optional[float] = None
    medication_count: int = Field(0, ge=0)
    medication_mg_total: float = Field(0, ge=0)  # combined daily dose, mg

    # Real diagnosis/outcome label (0 = no adverse outcome, 1 = adverse
    # outcome), supplied by the hospital's own clinical records — NOT
    # upload-time guesswork. Optional because not every hospital has one
    # wired up yet; Module 3's real_data.py documents exactly how it
    # handles records that arrive without one. Validated here (0/1 only)
    # so a malformed label fails the batch the same way a malformed vital
    # would, instead of silently reaching training.
    label: Optional[int] = Field(None, ge=0, le=1)

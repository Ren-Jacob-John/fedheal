"""
Patient cases, medical history, case-linked vitals, clinician review, and
doctor management (P0).

Built as a router factory so it reuses Module 1's existing dependencies
(get_current_user / require_role / get_db) instead of re-implementing auth.

Tenancy rules, enforced here and tested in test_cases.py:
  * hospital_id is ALWAYS taken from the authenticated user, never from a
    request body (a mismatching hospital_id in a doctor-create body is a 403).
  * Clinical data (cases, history, vitals-by-case, reviews) is readable and
    writable by CLINICIAN users of the owning hospital only. HOSPITAL_ADMIN
    manages people, not patients; SUPER_ADMIN is platform-level and has no
    access to patient-level data.
  * A case that exists in another hospital answers 403 and is audited;
    audit events carry ids only, never clinical content.
"""
import logging
from datetime import datetime, timezone
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

import auth
import models
from audit import audit_event

MAX_ITEMS = 50
MAX_ITEM_CHARS = 200
MAX_NOTE_CHARS = 2000


def _short_list(v):
    if v is None:
        return []
    if not isinstance(v, list):
        raise ValueError("must be a list of short strings")
    if len(v) > MAX_ITEMS:
        raise ValueError(f"at most {MAX_ITEMS} items")
    out = []
    for item in v:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("items must be non-empty strings")
        if len(item) > MAX_ITEM_CHARS:
            raise ValueError(f"items must be at most {MAX_ITEM_CHARS} characters")
        out.append(item.strip())
    return out


class DoctorCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=200)
    # Accepted only so a mismatch can be refused and audited; never used as the source of truth.
    hospital_id: Optional[str] = None


class DoctorOut(BaseModel):
    id: str
    hospital_id: str
    full_name: Optional[str]
    email: str
    role: models.Role
    is_active: bool
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class DoctorStatusUpdate(BaseModel):
    is_active: bool


class CaseCreate(BaseModel):
    patient_ref: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    admission_reason: str = Field(min_length=1, max_length=500)
    current_condition: Optional[str] = Field(default=None, max_length=64)
    presenting_symptoms: list[str] = Field(default_factory=list)

    @field_validator("presenting_symptoms")
    @classmethod
    def _sym(cls, v):
        return _short_list(v)


class CaseUpdate(BaseModel):
    admission_reason: Optional[str] = Field(default=None, min_length=1, max_length=500)
    current_condition: Optional[str] = Field(default=None, max_length=64)
    presenting_symptoms: Optional[list[str]] = None

    @field_validator("presenting_symptoms")
    @classmethod
    def _sym(cls, v):
        return None if v is None else _short_list(v)


class CaseOut(BaseModel):
    id: str
    hospital_id: str
    patient_ref: str
    encounter_id: str
    admission_reason: str
    current_condition: Optional[str]
    presenting_symptoms: list[str]
    status: str
    created_by: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class HistoryIn(BaseModel):
    conditions: list[str] = Field(default_factory=list)
    previous_diagnoses: list[str] = Field(default_factory=list)
    surgeries: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    family_history: list[str] = Field(default_factory=list)
    previous_admissions: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    notes: Optional[str] = Field(default=None, max_length=MAX_NOTE_CHARS)

    @field_validator("conditions", "previous_diagnoses", "surgeries", "allergies", "medications",
                     "family_history", "previous_admissions", "symptoms")
    @classmethod
    def _lists(cls, v):
        return _short_list(v)


class HistoryOut(HistoryIn):
    case_id: str
    hospital_id: str
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CaseVitalsIn(BaseModel):
    # One record. patient_ref and hospital are NOT accepted: they come from the case.
    record: dict


class ReviewIn(BaseModel):
    decision: Literal["ACCEPTED", "OVERRIDDEN", "NEEDS_MORE_DATA"]
    clinician_note: Optional[str] = Field(default=None, max_length=MAX_NOTE_CHARS)


class ReviewOut(BaseModel):
    review_id: str
    case_id: str
    doctor_id: str
    hospital_id: str
    decision: str
    note: Optional[str]
    created_at: Optional[datetime]


def build_router(*, get_db, get_current_user, require_role, validation_api_url, mint_validation_token,
                 stored_vitals_out, label_source, check_records, upload_limits, http_client_factory):
    router = APIRouter()
    admin_only = require_role(models.Role.HOSPITAL_ADMIN)
    clinician_only = require_role(models.Role.CLINICIAN)

    # ---------------- Doctor management (HOSPITAL_ADMIN) ----------------
    @router.post("/hospital/doctors", response_model=DoctorOut, status_code=201)
    def create_doctor(payload: DoctorCreate, request: Request, db: Session = Depends(get_db),
                      admin: models.User = Depends(admin_only)):
        if not admin.hospital_id:
            raise HTTPException(status_code=400, detail="Hospital admin has no hospital")
        if payload.hospital_id is not None and payload.hospital_id != admin.hospital_id:
            audit_event("cross_tenant.attempt", "denied", request=request, actor_user_id=admin.id,
                        actor_role=admin.role, hospital_id=admin.hospital_id,
                        requested_hospital_id=payload.hospital_id, resource_type="doctor")
            raise HTTPException(status_code=403, detail="Cannot create a doctor for another hospital")
        if db.query(models.User).filter(models.User.email == payload.email).first():
            raise HTTPException(status_code=400, detail="Email already registered")
        doctor = models.User(
            email=payload.email, full_name=payload.full_name,
            hashed_password=auth.hash_password(payload.password),
            role=models.Role.CLINICIAN, hospital_id=admin.hospital_id, is_active=True,
        )
        db.add(doctor)
        db.commit()
        db.refresh(doctor)
        audit_event("doctor.create", "success", request=request, actor_user_id=admin.id,
                    actor_role=admin.role, hospital_id=admin.hospital_id,
                    target_user_id=doctor.id, target_role=doctor.role)
        return doctor

    @router.get("/hospital/doctors", response_model=list[DoctorOut])
    def list_doctors(db: Session = Depends(get_db), admin: models.User = Depends(admin_only)):
        return (db.query(models.User)
                .filter(models.User.hospital_id == admin.hospital_id, models.User.role == models.Role.CLINICIAN)
                .order_by(models.User.created_at).all())

    @router.patch("/hospital/doctors/{doctor_id}", response_model=DoctorOut)
    def set_doctor_status(doctor_id: str, payload: DoctorStatusUpdate, request: Request,
                          db: Session = Depends(get_db), admin: models.User = Depends(admin_only)):
        doctor = db.query(models.User).filter(models.User.id == doctor_id).first()
        if doctor is None or doctor.role != models.Role.CLINICIAN:
            raise HTTPException(status_code=404, detail="Doctor not found")
        if doctor.hospital_id != admin.hospital_id:
            audit_event("cross_tenant.attempt", "denied", request=request, actor_user_id=admin.id,
                        actor_role=admin.role, hospital_id=admin.hospital_id,
                        target_hospital_id=doctor.hospital_id, resource_type="doctor")
            raise HTTPException(status_code=403, detail="Not permitted for this hospital's users")
        doctor.is_active = payload.is_active
        db.commit()
        db.refresh(doctor)
        audit_event("doctor.status", "success", request=request, actor_user_id=admin.id,
                    actor_role=admin.role, hospital_id=admin.hospital_id,
                    target_user_id=doctor.id, is_active=doctor.is_active)
        return doctor

    # ---------------- Case access helper ----------------
    def _own_case(db: Session, request: Request, user: models.User, case_id: str) -> models.Case:
        case = db.query(models.Case).filter(models.Case.id == case_id).first()
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        if case.hospital_id != user.hospital_id:
            audit_event("cross_tenant.attempt", "denied", request=request, actor_user_id=user.id,
                        actor_role=user.role, hospital_id=user.hospital_id,
                        target_hospital_id=case.hospital_id, case_id=case_id, resource_type="case")
            raise HTTPException(status_code=403, detail="Not permitted for this hospital's cases")
        return case

    # ---------------- Cases ----------------
    @router.post("/cases", response_model=CaseOut, status_code=201)
    def create_case(payload: CaseCreate, request: Request, db: Session = Depends(get_db),
                    user: models.User = Depends(clinician_only)):
        case = models.Case(
            hospital_id=user.hospital_id, patient_ref=payload.patient_ref,
            admission_reason=payload.admission_reason, current_condition=payload.current_condition,
            presenting_symptoms=payload.presenting_symptoms, created_by=user.id,
            status=models.CaseStatus.OPEN.value,
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        audit_event("case.create", "success", request=request, actor_user_id=user.id, actor_role=user.role,
                    hospital_id=user.hospital_id, case_id=case.id, resource_type="case")
        return case

    @router.get("/cases", response_model=list[CaseOut])
    def list_cases(request: Request, limit: int = 100, db: Session = Depends(get_db),
                   user: models.User = Depends(clinician_only)):
        limit = max(1, min(limit, 500))
        rows = (db.query(models.Case).filter(models.Case.hospital_id == user.hospital_id)
                .order_by(models.Case.created_at.desc()).limit(limit).all())
        audit_event("case.list", "success", request=request, actor_user_id=user.id, actor_role=user.role,
                    hospital_id=user.hospital_id, count=len(rows), resource_type="case")
        return rows

    @router.get("/cases/{case_id}", response_model=CaseOut)
    def get_case(case_id: str, request: Request, db: Session = Depends(get_db),
                 user: models.User = Depends(clinician_only)):
        case = _own_case(db, request, user, case_id)
        audit_event("case.read", "success", request=request, actor_user_id=user.id, actor_role=user.role,
                    hospital_id=user.hospital_id, case_id=case.id, resource_type="case")
        return case

    @router.patch("/cases/{case_id}", response_model=CaseOut)
    def update_case(case_id: str, payload: CaseUpdate, request: Request, db: Session = Depends(get_db),
                    user: models.User = Depends(clinician_only)):
        case = _own_case(db, request, user, case_id)
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            if k in ("admission_reason", "presenting_symptoms") and v is None:
                continue
            setattr(case, k, v)
        db.commit()
        db.refresh(case)
        audit_event("case.update", "success", request=request, actor_user_id=user.id, actor_role=user.role,
                    hospital_id=user.hospital_id, case_id=case.id, resource_type="case")
        return case

    # ---------------- Medical history ----------------
    @router.put("/cases/{case_id}/history", response_model=HistoryOut)
    def put_history(case_id: str, payload: HistoryIn, request: Request, db: Session = Depends(get_db),
                    user: models.User = Depends(clinician_only)):
        case = _own_case(db, request, user, case_id)
        row = db.query(models.MedicalHistory).filter(models.MedicalHistory.case_id == case.id).first()
        data = payload.model_dump()
        if row is None:
            row = models.MedicalHistory(case_id=case.id, hospital_id=case.hospital_id,
                                        created_by=user.id, **data)
            db.add(row)
        else:
            for k, v in data.items():
                setattr(row, k, v)
        db.commit()
        db.refresh(row)
        audit_event("history.write", "success", request=request, actor_user_id=user.id, actor_role=user.role,
                    hospital_id=user.hospital_id, case_id=case.id, resource_type="medical_history")
        return row

    @router.get("/cases/{case_id}/history", response_model=HistoryOut)
    def get_history(case_id: str, request: Request, db: Session = Depends(get_db),
                    user: models.User = Depends(clinician_only)):
        case = _own_case(db, request, user, case_id)
        row = db.query(models.MedicalHistory).filter(models.MedicalHistory.case_id == case.id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="No medical history recorded for this case")
        audit_event("history.read", "success", request=request, actor_user_id=user.id, actor_role=user.role,
                    hospital_id=user.hospital_id, case_id=case.id, resource_type="medical_history")
        return row

    # ---------------- Case-linked vitals ----------------
    @router.post("/cases/{case_id}/vitals")
    async def add_case_vitals(case_id: str, payload: CaseVitalsIn, request: Request,
                              db: Session = Depends(get_db), user: models.User = Depends(clinician_only)):
        """Single record, validated by Module 2 exactly like a bulk upload.
        Rejected records are never stored and the reasons are returned."""
        case = _own_case(db, request, user, case_id)
        hospital = db.query(models.Hospital).filter(models.Hospital.id == user.hospital_id).first()
        raw = {k: v for k, v in payload.record.items() if k not in ("hospital_id",)}
        raw["patient_ref"] = case.patient_ref            # the case decides the patient, not the body
        check_records([raw], upload_limits)
        try:
            async with http_client_factory(timeout=10.0) as client:
                resp = await client.post(
                    f"{validation_api_url}/validate/vitals",
                    headers={"X-Service-Key": mint_validation_token(user.hospital_id)},
                    json={"records": [raw], "hospital_id": user.hospital_id,
                          "require_label": bool(hospital.requires_label) if hospital else False},
                )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Could not reach Module 2 (validation service): {e}")
        result = resp.json()["results"][0]
        if result["status"] not in ("passed", "flagged"):
            audit_event("vitals.case_add", "denied", request=request, actor_user_id=user.id,
                        actor_role=user.role, hospital_id=user.hospital_id, case_id=case.id,
                        reason="validation_rejected")
            raise HTTPException(status_code=422, detail={"status": result["status"],
                                                         "reasons": result.get("reasons", [])})
        record = models.VitalsRecord(
            hospital_id=user.hospital_id, case_id=case.id, patient_ref=case.patient_ref,
            age_years=raw["age_years"], height_cm=raw["height_cm"], weight_kg=raw["weight_kg"],
            systolic_bp=raw.get("systolic_bp"), diastolic_bp=raw.get("diastolic_bp"),
            heart_rate_bpm=raw.get("heart_rate_bpm"),
            medication_count=raw.get("medication_count", 0),
            medication_mg_total=raw.get("medication_mg_total", 0),
            label=raw.get("label"), label_source=label_source(raw.get("label")),
            validation_status=result["status"],
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        audit_event("vitals.case_add", "success", request=request, actor_user_id=user.id,
                    actor_role=user.role, hospital_id=user.hospital_id, case_id=case.id,
                    record_id=record.id, status_code=200)
        return {"record_id": record.id, "validation_status": result["status"],
                "reasons": result.get("reasons", [])}

    @router.get("/cases/{case_id}/vitals", response_model=list[stored_vitals_out])
    def list_case_vitals(case_id: str, request: Request, db: Session = Depends(get_db),
                         user: models.User = Depends(clinician_only)):
        case = _own_case(db, request, user, case_id)
        return (db.query(models.VitalsRecord)
                .filter(models.VitalsRecord.case_id == case.id,
                        models.VitalsRecord.hospital_id == user.hospital_id)
                .order_by(models.VitalsRecord.uploaded_at.desc()).all())

    # ---------------- Clinician review ----------------
    @router.post("/cases/{case_id}/review", response_model=ReviewOut, status_code=201)
    def review_case(case_id: str, payload: ReviewIn, request: Request, db: Session = Depends(get_db),
                    user: models.User = Depends(clinician_only)):
        case = _own_case(db, request, user, case_id)
        review = models.ClinicianReview(case_id=case.id, hospital_id=user.hospital_id, doctor_id=user.id,
                                        decision=payload.decision, note=payload.clinician_note)
        db.add(review)
        case.status = (models.CaseStatus.NEEDS_MORE_DATA.value if payload.decision == "NEEDS_MORE_DATA"
                       else models.CaseStatus.REVIEWED.value)
        db.commit()
        db.refresh(review)
        audit_event("clinician.review", "success", request=request, actor_user_id=user.id,
                    actor_role=user.role, hospital_id=user.hospital_id, case_id=case.id,
                    resource_type="review", resource_id=review.id, decision=payload.decision)
        return ReviewOut(review_id=review.id, case_id=review.case_id, doctor_id=review.doctor_id,
                         hospital_id=review.hospital_id, decision=review.decision, note=review.note,
                         created_at=review.created_at)

    @router.get("/cases/{case_id}/reviews", response_model=list[ReviewOut])
    def list_reviews(case_id: str, request: Request, db: Session = Depends(get_db),
                     user: models.User = Depends(clinician_only)):
        case = _own_case(db, request, user, case_id)
        rows = (db.query(models.ClinicianReview)
                .filter(models.ClinicianReview.case_id == case.id,
                        models.ClinicianReview.hospital_id == user.hospital_id)
                .order_by(models.ClinicianReview.created_at).all())
        return [ReviewOut(review_id=r.id, case_id=r.case_id, doctor_id=r.doctor_id,
                          hospital_id=r.hospital_id, decision=r.decision, note=r.note,
                          created_at=r.created_at) for r in rows]

    return router

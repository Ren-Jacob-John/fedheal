"""
Module 1 — Authentication & Multi-Tenancy

Run: uvicorn main:app --reload --port 8001
Docs: http://localhost:8001/docs

This is the foundation module: every other service (validation, training,
dashboard) should treat "which hospital does this request belong to" as
answered by this service's JWT, never by a client-supplied field.
"""
import os
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
from database import engine, get_db, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(title="FedHeal Auth Service", version="0.1.0")

# Dev-only: wide open CORS so Module 4 (dashboard) can call this freely while
# everything runs on localhost. Lock this down to real origins before deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Module 2 (validation) — every vitals upload gets forwarded here before
# anything is stored. Module 1 never re-implements the validation rules.
VALIDATION_API_URL = os.environ.get("FEDHEAL_VALIDATION_API_URL", "http://localhost:8002")

# A hospital needs at least this many stored (passed+flagged) records before
# /training-status reports it as ready — an arbitrary but honest floor so
# the dashboard doesn't claim "ready for training" after one test upload.
MIN_RECORDS_FOR_TRAINING = 10


# ---------- Schemas ----------

class HospitalCreate(BaseModel):
    name: str


class HospitalStatusUpdate(BaseModel):
    is_active: bool


class HospitalOut(BaseModel):
    id: str
    name: str
    is_active: bool

    class Config:
        from_attributes = True


class UserRegister(BaseModel):
    email: str
    password: str
    hospital_id: str
    role: models.Role = models.Role.CLINICIAN


class UserOut(BaseModel):
    id: str
    email: str
    role: models.Role
    hospital_id: Optional[str]

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Vitals upload/export schemas (wires Module 2 -> here -> Module 3) ----------

class VitalsUploadRequest(BaseModel):
    # Raw dicts, on purpose — Module 2 owns schema validation, this service
    # shouldn't duplicate/drift from its pydantic model. hospital_id is
    # deliberately NOT a field here: it comes from the caller's JWT only.
    records: list[dict]


class VitalsUploadResponse(BaseModel):
    total: int
    passed: int
    flagged: int
    rejected: int
    stored: int
    results: list[dict]


class StoredVitalsOut(BaseModel):
    patient_ref: str
    age_years: float
    height_cm: float
    weight_kg: float
    systolic_bp: Optional[float]
    diastolic_bp: Optional[float]
    heart_rate_bpm: Optional[float]
    medication_count: int
    medication_mg_total: float
    label: Optional[int]
    validation_status: str

    class Config:
        from_attributes = True


# ---------- Auth dependency ----------

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = auth.decode_access_token(token)
    if payload is None:
        raise credentials_exception
    user_id = payload.get("sub")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user


def require_role(*allowed_roles: models.Role):
    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Not permitted for this role")
        return user
    return checker


# ---------- Hospital onboarding (super-admin only in practice) ----------

@app.post("/hospitals", response_model=HospitalOut)
def create_hospital(payload: HospitalCreate, db: Session = Depends(get_db)):
    existing = db.query(models.Hospital).filter(models.Hospital.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Hospital already exists")
    hospital = models.Hospital(name=payload.name)
    db.add(hospital)
    db.commit()
    db.refresh(hospital)
    return hospital


@app.get("/hospitals", response_model=list[HospitalOut])
def list_hospitals(db: Session = Depends(get_db)):
    return db.query(models.Hospital).all()


# Added for Module 7 (Admin/Platform): the operator's "activate/deactivate
# a hospital" action ultimately has to land here, since this is the only
# place the hospitals table actually lives.
@app.patch("/hospitals/{hospital_id}", response_model=HospitalOut)
def set_hospital_status(
    hospital_id: str,
    payload: HospitalStatusUpdate,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_role(models.Role.SUPER_ADMIN)),
):
    hospital = db.query(models.Hospital).filter(models.Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
    hospital.is_active = payload.is_active
    db.commit()
    db.refresh(hospital)
    return hospital


# ---------- User registration & login ----------

@app.post("/register", response_model=UserOut)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    hospital = db.query(models.Hospital).filter(models.Hospital.id == payload.hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")

    user = models.User(
        email=payload.email,
        hashed_password=auth.hash_password(payload.password),
        role=payload.role,
        hospital_id=payload.hospital_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = auth.create_access_token(
        data={"sub": user.id, "hospital_id": user.hospital_id, "role": user.role.value}
    )
    return Token(access_token=token)


@app.get("/me", response_model=UserOut)
def read_me(current_user: models.User = Depends(get_current_user)):
    return current_user


# ---------- Vitals upload (Module 2 wiring) ----------
# This is the endpoint the dashboard's new upload form calls, and the
# missing link both Module 2's and Module 3's READMEs called out as
# next-sprint work: hospital uploads -> validated here (by forwarding to
# Module 2, not reimplementing its rules) -> passed/flagged records land
# in this hospital's own VitalsRecord rows -> Module 3 can train on them.

@app.post("/vitals/upload", response_model=VitalsUploadResponse)
async def upload_vitals(
    payload: VitalsUploadRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="Only hospital-scoped users can upload vitals")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{VALIDATION_API_URL}/validate/vitals",
                json={"records": payload.records, "hospital_id": current_user.hospital_id},
            )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Module 2 (validation service): {e}")

    validation = resp.json()

    # Map validated results back to the raw records they came from (same
    # order Module 2 received them in) so we know exactly which raw dict to
    # store for each "passed"/"flagged" result.
    stored = 0
    for raw, result in zip(payload.records, validation["results"]):
        if result["status"] not in ("passed", "flagged"):
            continue
        record = models.VitalsRecord(
            hospital_id=current_user.hospital_id,
            patient_ref=result["patient_ref"] or raw.get("patient_ref", ""),
            age_years=raw["age_years"],
            height_cm=raw["height_cm"],
            weight_kg=raw["weight_kg"],
            systolic_bp=raw.get("systolic_bp"),
            diastolic_bp=raw.get("diastolic_bp"),
            heart_rate_bpm=raw.get("heart_rate_bpm"),
            medication_count=raw.get("medication_count", 0),
            medication_mg_total=raw.get("medication_mg_total", 0),
            label=raw.get("label"),
            validation_status=result["status"],
        )
        db.add(record)
        stored += 1
    db.commit()

    return VitalsUploadResponse(
        total=validation["total"],
        passed=validation["passed"],
        flagged=validation["flagged"],
        rejected=validation["rejected"],
        stored=stored,
        results=validation["results"],
    )


# ---------- Vitals export (Module 3 wiring) ----------
# Service-to-service only (not a human JWT) — this is what
# module3-fedlearning/real_data.py calls to pull a hospital's validated
# vitals instead of synthetic data. Only ever returns what's already been
# through Module 2's checks; never raw unvalidated uploads.

@app.get("/vitals/export", response_model=list[StoredVitalsOut])
def export_vitals(
    hospital_id: str,
    include_flagged: bool = False,
    db: Session = Depends(get_db),
    _=Depends(auth.require_service_key),
):
    query = db.query(models.VitalsRecord).filter(models.VitalsRecord.hospital_id == hospital_id)
    if not include_flagged:
        query = query.filter(models.VitalsRecord.validation_status == "passed")
    return query.all()


# ---------- Training status — real, backed by stored vitals ----------
# Replaces the earlier FAKE_TRAINING_STATUS_DB placeholder. "Training
# rounds" themselves still live in Module 7 (it's the module that talks to
# Module 3), so this reports what Module 1 actually owns: how much
# validated data each hospital has waiting, and whether that's enough to
# be worth a round.

def _hospital_training_status(db: Session, hospital_id: str) -> dict:
    count = (
        db.query(func.count(models.VitalsRecord.id))
        .filter(models.VitalsRecord.hospital_id == hospital_id)
        .scalar()
        or 0
    )
    last_upload = (
        db.query(func.max(models.VitalsRecord.uploaded_at))
        .filter(models.VitalsRecord.hospital_id == hospital_id)
        .scalar()
    )
    return {
        "records_available": count,
        "status": "ready_for_training" if count >= MIN_RECORDS_FOR_TRAINING else "collecting_data",
        "last_upload": last_upload.isoformat() if last_upload else None,
    }


@app.get("/training-status")
def get_training_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == models.Role.SUPER_ADMIN:
        hospital_ids = [h.id for h in db.query(models.Hospital).all()]
        return {hid: _hospital_training_status(db, hid) for hid in hospital_ids}
    return _hospital_training_status(db, current_user.hospital_id)

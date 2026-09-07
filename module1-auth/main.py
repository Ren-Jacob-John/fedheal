"""
Module 1 — Authentication & Multi-Tenancy

Run: uvicorn main:app --reload --port 8001
Docs: http://localhost:8001/docs

This is the foundation module: every other service (validation, training,
dashboard) should treat "which hospital does this request belong to" as
answered by this service's JWT, never by a client-supplied field.
"""
import io
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, Depends, HTTPException, Request, Response, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import models
from database import engine, get_db, Base
from docs_theme import mount_custom_docs

Base.metadata.create_all(bind=engine)

app = FastAPI(title="FedHeal Auth Service", version="0.1.0", docs_url=None)
mount_custom_docs(app, accent="#5b7cfa", accent_soft="#dfe7ff")  # blue — Module 1

# Locked to the real dashboard origin(s) via env var — comma-separated for
# multiple environments (e.g. local dev + a deployed preview URL). Falls
# back to the Vite dev server's default port so local dev keeps working
# out of the box, but this is no longer "*": a malicious page in someone's
# browser can no longer make authenticated requests here just because a
# logged-in user happened to visit it.
_dashboard_origins = os.environ.get("FEDHEAL_DASHBOARD_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _dashboard_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Rate limiting on /token ----------
# Simple in-memory sliding-window limiter, keyed by client IP + attempted
# username, so a slow drip of guesses against ONE account doesn't get
# lumped in with normal traffic from a shared IP (e.g. an office NAT).
# In-memory is fine for a single-process dev/demo deployment; a real
# multi-worker deployment needs this backed by Redis or similar so limits
# are shared across processes instead of reset per worker.
_LOGIN_ATTEMPT_WINDOW_SECONDS = 60
_LOGIN_ATTEMPT_MAX = 5
_login_attempts: dict[str, deque] = defaultdict(deque)


def _check_login_rate_limit(key: str) -> None:
    now = time.monotonic()
    attempts = _login_attempts[key]
    while attempts and now - attempts[0] > _LOGIN_ATTEMPT_WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= _LOGIN_ATTEMPT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts — try again in under {_LOGIN_ATTEMPT_WINDOW_SECONDS} seconds.",
        )
    attempts.append(now)

# auto_error=False so a request with no Authorization header doesn't 401
# before get_current_user gets a chance to check the httpOnly cookie
# instead — the browser dashboard now relies on the cookie, curl/API
# clients following this module's README still use the Bearer header.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# The dashboard used to keep the raw JWT in localStorage, readable by any
# JS running on the page (including an XSS payload, if one ever got in).
# Login now ALSO sets it as an httpOnly cookie the browser sends
# automatically and JS can never read; the JSON body still returns
# access_token too, for curl/API use exactly as this module's README
# documents — no need to break that flow. COOKIE_SECURE defaults off for
# local http dev; set FEDHEAL_COOKIE_SECURE=true once this is served over
# https.
TOKEN_COOKIE_NAME = "fedheal_token"
COOKIE_SECURE = os.environ.get("FEDHEAL_COOKIE_SECURE", "false").lower() == "true"

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
    id: str
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

def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Prefer an explicit Bearer header (curl/API clients); fall back to the
    # httpOnly cookie the browser dashboard now sends automatically.
    token = token or request.cookies.get(TOKEN_COOKIE_NAME)
    if token is None:
        raise credentials_exception
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
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate_limit(f"{client_ip}:{form_data.username}")

    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    token = auth.create_access_token(
        data={"sub": user.id, "hospital_id": user.hospital_id, "role": user.role.value}
    )
    response.set_cookie(
        key=TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=auth.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    return Token(access_token=token)


@app.post("/logout")
def logout(response: Response):
    response.delete_cookie(TOKEN_COOKIE_NAME, path="/")
    return {"status": "logged_out"}


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


# ---------- Vitals upload, CSV variant ----------
# Same job as /vitals/upload, but for a hospital's CSV export instead of
# hand-built JSON — forwards the raw file to Module 2's CSV endpoint, then
# stores exactly the same way the JSON path does. Kept as a thin wrapper
# rather than duplicating the storage loop.

@app.post("/vitals/upload/csv", response_model=VitalsUploadResponse)
async def upload_vitals_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="Only hospital-scoped users can upload vitals")

    raw_bytes = await file.read()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{VALIDATION_API_URL}/validate/vitals/csv",
                files={"file": (file.filename, raw_bytes, "text/csv")},
                data={"hospital_id": current_user.hospital_id},
            )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Module 2 (validation service): {e}")

    validation = resp.json()

    # Re-parse the same CSV here (cheap, and keeps this endpoint from having
    # to trust a second copy of "what the raw records were" over the wire)
    # so we can store passed/flagged rows the same way the JSON path does.
    import csv as _csv
    reader = _csv.DictReader(io.StringIO(raw_bytes.decode("utf-8")))
    raw_rows = list(reader)

    stored = 0
    for raw, result in zip(raw_rows, validation["results"]):
        if result["status"] not in ("passed", "flagged"):
            continue

        def _num(v, cast):
            if v in (None, ""):
                return None
            return cast(v)

        record = models.VitalsRecord(
            hospital_id=current_user.hospital_id,
            patient_ref=result["patient_ref"] or raw.get("patient_ref", ""),
            age_years=_num(raw.get("age_years"), float),
            height_cm=_num(raw.get("height_cm"), float),
            weight_kg=_num(raw.get("weight_kg"), float),
            systolic_bp=_num(raw.get("systolic_bp"), float),
            diastolic_bp=_num(raw.get("diastolic_bp"), float),
            heart_rate_bpm=_num(raw.get("heart_rate_bpm"), float),
            medication_count=int(_num(raw.get("medication_count"), float) or 0),
            medication_mg_total=_num(raw.get("medication_mg_total"), float) or 0,
            label=_num(raw.get("label"), int),
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


# ---------- Flagged-record review (human-in-the-loop) ----------
# Closes the gap both this module's and Module 2's READMEs called out:
# flagged records were stored but never surfaced for a human to actually
# look at. A hospital_admin/clinician can list their own hospital's
# flagged records and approve (-> "passed", eligible for training) or
# reject (-> deleted, same as if Module 2 had rejected it outright)
# each one. Scoped by JWT hospital_id like every other endpoint here —
# never trusts a client-supplied hospital_id.

class ReviewDecision(BaseModel):
    decision: str  # "approve" | "reject"


@app.get("/vitals/flagged", response_model=list[StoredVitalsOut])
def list_flagged_vitals(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="Only hospital-scoped users can review vitals")
    return (
        db.query(models.VitalsRecord)
        .filter(
            models.VitalsRecord.hospital_id == current_user.hospital_id,
            models.VitalsRecord.validation_status == "flagged",
        )
        .all()
    )


@app.post("/vitals/{record_id}/review")
def review_flagged_vitals(
    record_id: str,
    payload: ReviewDecision,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.Role.HOSPITAL_ADMIN, models.Role.SUPER_ADMIN)
    ),
):
    record = db.query(models.VitalsRecord).filter(models.VitalsRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if current_user.role != models.Role.SUPER_ADMIN and record.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Not permitted for this hospital's records")
    if record.validation_status != "flagged":
        raise HTTPException(status_code=400, detail="Only flagged records can be reviewed")

    if payload.decision == "approve":
        record.validation_status = "passed"
        db.commit()
        return {"id": record_id, "validation_status": "passed"}
    elif payload.decision == "reject":
        db.delete(record)
        db.commit()
        return {"id": record_id, "deleted": True}
    else:
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")


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
    _=Depends(auth.require_module3_service_key),
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

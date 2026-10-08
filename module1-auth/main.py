"""
Module 1 — Authentication & Multi-Tenancy

Run: uvicorn main:app --reload --port 8001
Docs: http://localhost:8001/docs

This is the foundation module: every other service (validation, training,
dashboard) should treat "which hospital does this request belong to" as
answered by this service's JWT, never by a client-supplied field.
"""
import io
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, Depends, Header, HTTPException, Request, Response, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth
import config
import limits
import models
import service_auth
from audit import audit_event, hash_identifier
from database import get_db
from docs_theme import mount_custom_docs

# Sprint A introduced Alembic (see migrations/ and module1-auth.md) but kept
# Base.metadata.create_all() running alongside it as a transitional safety
# net. Sprint B retires create_all entirely: `alembic upgrade head` is now
# the only way tables come into existence, in every environment including
# local dev. Running both permanently would be worse than either alone —
# create_all would silently create any table a forgotten migration missed,
# and the schema Alembic thinks is deployed would drift from the one
# actually deployed. See module1-auth.md's "Database schema" section for
# the one-time `alembic stamp` step existing databases need.

app = FastAPI(title="FedHeal Auth Service", version="0.1.0", docs_url=None)
mount_custom_docs(app, accent="#5b7cfa", accent_soft="#dfe7ff")  # blue — Module 1

# Upload size limits (see limits.py). Added BEFORE the CORS middleware so
# CORS wraps it: a 413 still carries CORS headers and the browser can show
# the real error instead of an opaque network failure.
UPLOAD_LIMITS = limits.UploadLimits.from_env()
app.add_middleware(
    limits.BodySizeLimitMiddleware,
    limits={
        "/vitals/upload": UPLOAD_LIMITS.max_json_body_bytes,
        "/vitals/upload/csv": UPLOAD_LIMITS.max_csv_bytes + limits.MULTIPART_OVERHEAD_BYTES,
    },
)

# CORS: explicit origins from FEDHEAL_DASHBOARD_ORIGIN (never "*"; required
# and https-only in staging/production — see config.cors_settings) and only
# the methods/headers the dashboard actually uses against this service.
app.add_middleware(
    CORSMiddleware,
    **config.cors_settings(methods=("GET", "POST", "PATCH", "PUT"), headers=("Authorization", "Content-Type")),
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
# local http dev only; staging/production always set it (config.cookie_secure).
TOKEN_COOKIE_NAME = "fedheal_token"
COOKIE_SECURE = config.cookie_secure()  # always True outside development/test

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
    # Sprint A: declare up front whether this hospital supplies real
    # clinical outcome labels. See models.Hospital.requires_label.
    requires_label: bool = False


class HospitalStatusUpdate(BaseModel):
    """
    Both fields optional so PATCH can change either independently —
    Module 7's existing set_hospital_status() sends {"is_active": ...}
    and keeps working untouched.
    """
    is_active: Optional[bool] = None
    requires_label: Optional[bool] = None


class HospitalOut(BaseModel):
    id: str
    name: str
    is_active: bool
    requires_label: bool

    class Config:
        from_attributes = True


class UserRegister(BaseModel):
    """
    Public self-service registration (POST /register — no auth required).

    There is deliberately no `role` field here. Every account created
    through this endpoint is a CLINICIAN, full stop — pydantic silently
    drops any field a client sends that isn't declared on this model, so
    a spoofed `"role": "super_admin"` in the request body has no effect
    on what gets written to the database. Elevated accounts (hospital
    admins, other super admins) are only ever created through the
    SUPER_ADMIN-gated POST /admin/users below.
    """
    email: str
    password: str
    hospital_id: str


class AdminUserCreate(BaseModel):
    """
    Used only by POST /admin/users, which is itself gated to an
    authenticated SUPER_ADMIN by require_role() below — the same
    dependency every other role-restricted endpoint in this module
    uses. `role` is safe to accept here specifically *because* the
    caller has already proven they're a SUPER_ADMIN before this model
    is even parsed; that's what makes this different from the public
    UserRegister schema above, which never exposes it.
    """
    email: str
    password: str
    role: models.Role
    # Optional: a new SUPER_ADMIN isn't tied to one hospital (mirrors
    # models.User.hospital_id, which is nullable for the same reason).
    # A new HOSPITAL_ADMIN must supply one — enforced in the endpoint.
    hospital_id: Optional[str] = None


class UserOut(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    is_active: bool = True
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
    # Sprint A: how many of the stored records carry a real label, and
    # whether this hospital was held to the requirement. Surfaced in the
    # response (not just buried in the DB) so the uploader finds out at
    # upload time that their export dropped the label column — rather
    # than at training time, three days later, in someone else's logs.
    label_required: bool = False
    stored_labeled: int = 0
    stored_unlabeled: int = 0


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
    label_source: str
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
        audit_event("authn.failure", "denied", request=request, reason="missing_credentials",
                    level=logging.INFO)
        raise credentials_exception
    payload, why = auth.inspect_access_token(token)
    if payload is None:
        audit_event("authn.failure", "denied", request=request, reason=f"{why}_token")
        raise credentials_exception
    user_id = payload.get("sub")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        audit_event("authn.failure", "denied", request=request, reason="unknown_user")
        raise credentials_exception
    if user.is_active is False:
        audit_event("authn.failure", "denied", request=request, reason="account_disabled")
        raise credentials_exception
    return user


def require_role(*allowed_roles: models.Role):
    def checker(request: Request, user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in allowed_roles:
            audit_event(
                "authz.denied", "denied", request=request,
                actor_user_id=user.id, actor_role=user.role, hospital_id=user.hospital_id,
                required_roles=",".join(r.value for r in allowed_roles),
            )
            raise HTTPException(status_code=403, detail="Not permitted for this role")
        return user
    return checker


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Hospital onboarding (SUPER_ADMIN only) ----------

@app.post("/hospitals", response_model=HospitalOut)
def create_hospital(
    payload: HospitalCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_role(models.Role.SUPER_ADMIN)),
):
    existing = db.query(models.Hospital).filter(models.Hospital.name == payload.name).first()
    if existing:
        audit_event("hospital.create", "failure", request=request, actor_user_id=admin.id,
                    actor_role=admin.role, reason="duplicate_name")
        raise HTTPException(status_code=400, detail="Hospital already exists")
    hospital = models.Hospital(name=payload.name, requires_label=payload.requires_label)
    db.add(hospital)
    db.commit()
    db.refresh(hospital)
    audit_event("hospital.create", "success", request=request, actor_user_id=admin.id,
                actor_role=admin.role, target_hospital_id=hospital.id,
                requires_label=hospital.requires_label)
    return hospital


@dataclass
class DirectoryPrincipal:
    """Who is asking for the hospital list, and which hospitals that entitles
    them to see: None = all, otherwise exactly one hospital id."""
    scope: Optional[str]
    user: Optional[models.User] = None
    service: Optional[str] = None


def get_directory_principal(
    request: Request,
    x_service_key: str | None = Header(default=None),
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> DirectoryPrincipal:
    """
    GET /hospitals accepts EITHER a logged-in user (same JWT as everywhere
    else) OR a hospital-scoped Module 3 service credential. Anonymous -> 401.
    """
    if x_service_key is not None:
        try:
            claims = auth.verify_directory_credential(x_service_key)
        except HTTPException as exc:
            audit_event("authn.failure", "denied", request=request, actor_service="module3",
                        reason="service_credential_" + ("invalid" if exc.status_code == 401 else "not_permitted"))
            raise
        hid = service_auth.hospital_scope(claims)
        # A wildcard is only meaningful on a directory-audience token; an
        # export-audience token never widens beyond its own hospital.
        if hid == service_auth.ANY_HOSPITAL and claims.get("aud") == service_auth.AUD_HOSPITAL_DIRECTORY:
            return DirectoryPrincipal(scope=None, service=claims["sub"])
        return DirectoryPrincipal(scope=hid if hid and hid != service_auth.ANY_HOSPITAL else "", service=claims["sub"])
    # Any authenticated user: the dashboard's federation map is documented
    # to place a node for EVERY hospital in the federation (id / name /
    # active flag), so logged-in users get the full directory. Anonymous
    # callers get nothing.
    user = get_current_user(request, token, db)
    return DirectoryPrincipal(scope=None, user=user)


@app.get("/hospitals", response_model=list[HospitalOut])
def list_hospitals(
    request: Request,
    db: Session = Depends(get_db),
    principal: DirectoryPrincipal = Depends(get_directory_principal),
):
    """
    Authenticated (was an anonymous directory). Any logged-in user sees the
    full minimal directory the federation map needs; Module 3's credentials
    are narrower — a hospital-scoped service token sees only its own
    hospital, and only the operator's directory-audience token sees all.
    Nothing here returns vitals or user data.
    """
    query = db.query(models.Hospital)
    if principal.scope is not None:
        query = query.filter(models.Hospital.id == principal.scope)
    return query.all()


# Added for Module 7 (Admin/Platform): the operator's "activate/deactivate
# a hospital" action ultimately has to land here, since this is the only
# place the hospitals table actually lives.
@app.patch("/hospitals/{hospital_id}", response_model=HospitalOut)
def set_hospital_status(
    hospital_id: str,
    payload: HospitalStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_role(models.Role.SUPER_ADMIN)),
):
    hospital = db.query(models.Hospital).filter(models.Hospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
    if payload.is_active is None and payload.requires_label is None:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of 'is_active' or 'requires_label'",
        )
    if payload.is_active is not None:
        hospital.is_active = payload.is_active
    if payload.requires_label is not None:
        hospital.requires_label = payload.requires_label
    db.commit()
    db.refresh(hospital)
    audit_event("hospital.update", "success", request=request, actor_user_id=_admin.id,
                actor_role=_admin.role, target_hospital_id=hospital.id,
                is_active=hospital.is_active, requires_label=hospital.requires_label)
    return hospital


# ---------- User registration & login ----------

@app.post("/register", response_model=UserOut)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    hospital = db.query(models.Hospital).filter(models.Hospital.id == payload.hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")

    # Public registration always creates a CLINICIAN. This is hard-coded,
    # not read from `payload` — UserRegister has no role field, and even
    # if a caller sends one in the raw JSON body it's silently ignored,
    # never reaching this line.
    user = models.User(
        email=payload.email,
        hashed_password=auth.hash_password(payload.password),
        role=models.Role.CLINICIAN,
        hospital_id=payload.hospital_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------- Administrator creation (SUPER_ADMIN only) ----------
# The only path by which a HOSPITAL_ADMIN or SUPER_ADMIN account can come
# into existence. Gated by require_role(SUPER_ADMIN) — the exact same
# dependency /hospitals/{id} PATCH already uses, not a parallel
# reimplementation of the role check — so the privilege check happens
# before this function body ever runs, which is what makes it safe to
# also permit role=SUPER_ADMIN here.

@app.post("/admin/users", response_model=UserOut)
def create_admin_user(
    payload: AdminUserCreate,
    request: Request,
    db: Session = Depends(get_db),
    _admin: models.User = Depends(require_role(models.Role.SUPER_ADMIN)),
):
    if payload.role not in (models.Role.HOSPITAL_ADMIN, models.Role.SUPER_ADMIN):
        raise HTTPException(
            status_code=400,
            detail="Use POST /register for clinician accounts; this endpoint creates administrators only",
        )

    if db.query(models.User).filter(models.User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    hospital_id = payload.hospital_id
    if payload.role == models.Role.HOSPITAL_ADMIN:
        if not hospital_id:
            raise HTTPException(status_code=400, detail="hospital_id is required for a hospital_admin")
        hospital = db.query(models.Hospital).filter(models.Hospital.id == hospital_id).first()
        if not hospital:
            raise HTTPException(status_code=404, detail="Hospital not found")
    # SUPER_ADMIN mirrors models.User.hospital_id: nullable, since a
    # platform-level admin isn't scoped to one tenant. If one is supplied
    # anyway it's kept as-is rather than silently dropped.

    user = models.User(
        email=payload.email,
        hashed_password=auth.hash_password(payload.password),
        role=payload.role,
        hospital_id=hospital_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit_event("admin.user_create", "success", request=request, actor_user_id=_admin.id,
                actor_role=_admin.role, target_user_id=user.id, target_role=user.role,
                target_hospital_id=user.hospital_id)
    return user


@app.post("/token", response_model=Token)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"
    try:
        _check_login_rate_limit(f"{client_ip}:{form_data.username}")
    except HTTPException:
        audit_event("login", "denied", request=request, reason="rate_limited",
                    username_hash=hash_identifier(form_data.username))
        raise

    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if user is not None and user.is_active is False:
        # Same response as a wrong password: don't reveal that the account exists.
        audit_event("login", "failure", request=request, reason="account_disabled",
                    username_hash=hash_identifier(form_data.username))
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        # Never the submitted name/password: a short hash lets repeated
        # attempts against one account be correlated without storing it.
        audit_event("login", "failure", request=request, reason="bad_credentials",
                    username_hash=hash_identifier(form_data.username))
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
    audit_event("login", "success", request=request, actor_user_id=user.id,
                actor_role=user.role, hospital_id=user.hospital_id)
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

def _require_upload_hospital(db: Session, current_user: models.User) -> models.Hospital:
    """
    Every upload path needs the caller's hospital ROW, not just its id —
    requires_label lives there. Resolved from the JWT's hospital_id like
    everything else here; never from the request body.
    """
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="Only hospital-scoped users can upload vitals")
    hospital = (
        db.query(models.Hospital)
        .filter(models.Hospital.id == current_user.hospital_id)
        .first()
    )
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return hospital


def _label_source(label) -> str:
    """
    Sprint A: record where the label came from at the moment it's stored.
    Only "hospital" or "missing" — see models.VitalsRecord.label_source for
    why there is no "placeholder" value here.
    """
    return "hospital" if label is not None else "missing"


@app.post("/vitals/upload", response_model=VitalsUploadResponse)
async def upload_vitals(
    payload: VitalsUploadRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hospital = _require_upload_hospital(db, current_user)
    limits.check_records(payload.records, UPLOAD_LIMITS)  # 413 before anything is forwarded or stored

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{VALIDATION_API_URL}/validate/vitals",
                headers={"X-Service-Key": auth.mint_validation_token(current_user.hospital_id)},
                json={
                    "records": payload.records,
                    "hospital_id": current_user.hospital_id,
                    # Module 2 owns the rule; Module 1 owns the tenant
                    # setting that decides whether it applies.
                    "require_label": hospital.requires_label,
                },
            )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Module 2 (validation service): {e}")

    validation = resp.json()

    # Map validated results back to the raw records they came from (same
    # order Module 2 received them in) so we know exactly which raw dict to
    # store for each "passed"/"flagged" result.
    stored = 0
    stored_labeled = 0
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
            label_source=_label_source(raw.get("label")),
            validation_status=result["status"],
        )
        db.add(record)
        stored += 1
        if record.label is not None:
            stored_labeled += 1
    db.commit()

    audit_event("vitals.upload", "success", request=request, actor_user_id=current_user.id,
                actor_role=current_user.role, hospital_id=current_user.hospital_id,
                total=validation["total"], stored=stored, rejected=validation["rejected"])
    return VitalsUploadResponse(
        total=validation["total"],
        passed=validation["passed"],
        flagged=validation["flagged"],
        rejected=validation["rejected"],
        stored=stored,
        results=validation["results"],
        label_required=hospital.requires_label,
        stored_labeled=stored_labeled,
        stored_unlabeled=stored - stored_labeled,
    )


# ---------- Vitals upload, CSV variant ----------
# Same job as /vitals/upload, but for a hospital's CSV export instead of
# hand-built JSON — forwards the raw file to Module 2's CSV endpoint, then
# stores exactly the same way the JSON path does. Kept as a thin wrapper
# rather than duplicating the storage loop.

@app.post("/vitals/upload/csv", response_model=VitalsUploadResponse)
async def upload_vitals_csv(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    hospital = _require_upload_hospital(db, current_user)

    raw_bytes = await file.read()
    if len(raw_bytes) > UPLOAD_LIMITS.max_csv_bytes:
        raise limits.too_large(f"CSV file too large (limit {UPLOAD_LIMITS.max_csv_bytes} bytes)")
    # Parse (and bound) the rows BEFORE forwarding, so an oversized CSV is
    # rejected here with 413 instead of costing a Module 2 round-trip.
    import csv as _csv
    try:
        reader = _csv.DictReader(io.StringIO(raw_bytes.decode("utf-8")))
        raw_rows = []
        for row in reader:
            raw_rows.append(row)
            if len(raw_rows) > UPLOAD_LIMITS.max_records:
                break
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded")
    limits.check_records(raw_rows, UPLOAD_LIMITS)
    if reader.fieldnames and len(reader.fieldnames) > UPLOAD_LIMITS.max_record_fields:
        raise limits.too_large(f"CSV has too many columns (limit {UPLOAD_LIMITS.max_record_fields})")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{VALIDATION_API_URL}/validate/vitals/csv",
                headers={"X-Service-Key": auth.mint_validation_token(current_user.hospital_id)},
                files={"file": (file.filename, raw_bytes, "text/csv")},
                data={
                    "hospital_id": current_user.hospital_id,
                    "require_label": str(hospital.requires_label).lower(),
                },
            )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Module 2 (validation service): {e}")

    validation = resp.json()

    # raw_rows was parsed above from the same bytes (keeps this endpoint from
    # having to trust a second copy of "what the raw records were" over the
    # wire) so we can store passed/flagged rows the same way the JSON path does.

    stored = 0
    stored_labeled = 0
    for raw, result in zip(raw_rows, validation["results"]):
        if result["status"] not in ("passed", "flagged"):
            continue

        def _num(v, cast):
            if v in (None, ""):
                return None
            return cast(v)

        _csv_label = _num(raw.get("label"), int)
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
            label=_csv_label,
            label_source=_label_source(_csv_label),
            validation_status=result["status"],
        )
        db.add(record)
        stored += 1
        if _csv_label is not None:
            stored_labeled += 1
    db.commit()

    audit_event("vitals.upload_csv", "success", request=request, actor_user_id=current_user.id,
                actor_role=current_user.role, hospital_id=current_user.hospital_id,
                total=validation["total"], stored=stored, rejected=validation["rejected"])
    return VitalsUploadResponse(
        total=validation["total"],
        passed=validation["passed"],
        flagged=validation["flagged"],
        rejected=validation["rejected"],
        stored=stored,
        results=validation["results"],
        label_required=hospital.requires_label,
        stored_labeled=stored_labeled,
        stored_unlabeled=stored - stored_labeled,
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
    # Constrained (was a free-form str): anything else is a 422 from
    # pydantic before the endpoint runs. The accepted values and what they
    # do are unchanged.
    decision: Literal["approve", "reject"]


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
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        require_role(models.Role.HOSPITAL_ADMIN, models.Role.SUPER_ADMIN)
    ),
):
    record = db.query(models.VitalsRecord).filter(models.VitalsRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    if current_user.role != models.Role.SUPER_ADMIN and record.hospital_id != current_user.hospital_id:
        audit_event("cross_tenant.attempt", "denied", request=request, actor_user_id=current_user.id,
                    actor_role=current_user.role, hospital_id=current_user.hospital_id,
                    target_hospital_id=record.hospital_id, record_id=record_id, decision=payload.decision)
        raise HTTPException(status_code=403, detail="Not permitted for this hospital's records")
    if record.validation_status != "flagged":
        raise HTTPException(status_code=400, detail="Only flagged records can be reviewed")

    if payload.decision == "approve":
        record.validation_status = "passed"
        db.commit()
        audit_event("vitals.review", "success", request=request, actor_user_id=current_user.id,
                    actor_role=current_user.role, hospital_id=record.hospital_id,
                    record_id=record_id, decision="approve")
        return {"id": record_id, "validation_status": "passed"}
    # payload.decision == "reject" (the Literal type guarantees nothing else gets here)
    hospital_of_record = record.hospital_id
    db.delete(record)
    db.commit()
    audit_event("vitals.review", "success", request=request, actor_user_id=current_user.id,
                actor_role=current_user.role, hospital_id=hospital_of_record,
                record_id=record_id, decision="reject")
    return {"id": record_id, "deleted": True}


# ---------- Vitals export (Module 3 wiring) ----------
# Service-to-service only (not a human JWT) — this is what
# module3-fedlearning/real_data.py calls to pull a hospital's validated
# vitals instead of synthetic data. Only ever returns what's already been
# through Module 2's checks; never raw unvalidated uploads.
#
# Tenant isolation: the credential is a signed token that names ONE
# hospital (see service_auth.py / mint_service_token.py). The hospital_id
# query parameter is only honoured if it equals the hospital in the token;
# any other value is a 403 and an audit event. There is no "all hospitals"
# export credential.

@app.get("/vitals/export", response_model=list[StoredVitalsOut])
def export_vitals(
    hospital_id: str,
    request: Request,
    include_flagged: bool = False,
    labeled_only: bool = True,
    db: Session = Depends(get_db),
    claims: dict = Depends(auth.require_export_credential),
):
    """
    BREAKING DEFAULT CHANGE (Sprint A): `labeled_only` defaults to **True**.

    Before, this returned unlabeled records too, and Module 3 quietly
    substituted a rule-based placeholder label for each one — meaning the
    default end-to-end path trained partly on labels no clinician ever
    produced. That default is now inverted: unlabeled records are excluded
    here unless a caller explicitly asks for them.

    Pass labeled_only=false to get the old behaviour. Module 3's
    real_data.py only does that when its own --allow-placeholder-labels
    flag is set, and it prints a loud banner when it happens.
    """
    token_hospital = service_auth.hospital_scope(claims)
    if not token_hospital or token_hospital == service_auth.ANY_HOSPITAL or token_hospital != hospital_id:
        audit_event("vitals.export", "denied", request=request, actor_service=claims.get("sub"),
                    reason="cross_tenant", requested_hospital_id=hospital_id,
                    token_hospital_id=token_hospital)
        raise HTTPException(status_code=403, detail="Credential is not authorized for this hospital")

    query = db.query(models.VitalsRecord).filter(models.VitalsRecord.hospital_id == token_hospital)
    if not include_flagged:
        query = query.filter(models.VitalsRecord.validation_status == "passed")
    if labeled_only:
        query = query.filter(models.VitalsRecord.label.isnot(None))
    rows = query.all()
    audit_event("vitals.export", "success", request=request, actor_service=claims.get("sub"),
                hospital_id=token_hospital, count=len(rows))
    return rows


# ---------- Stored-record read access (dashboard record picker, Module 8) ----------
# Registered AFTER /vitals/flagged and /vitals/export so the fixed paths win
# over the /vitals/{record_id} pattern.

@app.get("/vitals", response_model=list[StoredVitalsOut])
def list_vitals(
    request: Request,
    validation_status: Optional[Literal["passed", "flagged"]] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """The caller's own hospital's stored records (ordered by patient_ref,
    capped at 500). Same scoping rule as /vitals/flagged: the hospital comes from the
    JWT, never from a parameter."""
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="Only hospital-scoped users can list vitals")
    query = db.query(models.VitalsRecord).filter(models.VitalsRecord.hospital_id == current_user.hospital_id)
    if validation_status:
        query = query.filter(models.VitalsRecord.validation_status == validation_status)
    limit = max(1, min(limit, 500))
    rows = query.order_by(models.VitalsRecord.patient_ref).limit(limit).all()
    audit_event("vitals.list", "success", request=request, actor_user_id=current_user.id,
                actor_role=current_user.role, hospital_id=current_user.hospital_id, count=len(rows))
    return rows


@app.get("/vitals/{record_id}", response_model=StoredVitalsOut)
def get_vitals_record(
    record_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """One stored record. 404 if it doesn't exist; 403 (and an audit event)
    if it belongs to another hospital. Module 8 calls this with the user's
    own JWT — it holds no service credential for record access."""
    record = db.query(models.VitalsRecord).filter(models.VitalsRecord.id == record_id).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")
    if current_user.role != models.Role.SUPER_ADMIN and record.hospital_id != current_user.hospital_id:
        audit_event("cross_tenant.attempt", "denied", request=request, actor_user_id=current_user.id,
                    actor_role=current_user.role, hospital_id=current_user.hospital_id,
                    target_hospital_id=record.hospital_id, record_id=record_id)
        raise HTTPException(status_code=403, detail="Not permitted for this hospital's records")
    audit_event("vitals.read", "success", request=request, actor_user_id=current_user.id,
                actor_role=current_user.role, hospital_id=record.hospital_id, record_id=record_id)
    return record


# ---------- Cases, medical history, case vitals, clinician review, doctor management ----------
import cases as _cases  # noqa: E402

app.include_router(_cases.build_router(
    get_db=get_db, get_current_user=get_current_user, require_role=require_role,
    validation_api_url=VALIDATION_API_URL, mint_validation_token=auth.mint_validation_token,
    stored_vitals_out=StoredVitalsOut, label_source=_label_source, check_records=limits.check_records,
    upload_limits=UPLOAD_LIMITS, http_client_factory=lambda **kw: httpx.AsyncClient(**kw),
))


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
    # Sprint A: "how many records" stopped being the useful number once
    # unlabeled records were excluded from training by default. A hospital
    # can sit on 500 records and still be untrainable if none carry a real
    # outcome, and the old status field would have cheerfully reported
    # "ready_for_training" the whole time.
    labeled_count = (
        db.query(func.count(models.VitalsRecord.id))
        .filter(
            models.VitalsRecord.hospital_id == hospital_id,
            models.VitalsRecord.label.isnot(None),
        )
        .scalar()
        or 0
    )
    last_upload = (
        db.query(func.max(models.VitalsRecord.uploaded_at))
        .filter(models.VitalsRecord.hospital_id == hospital_id)
        .scalar()
    )
    hospital = db.query(models.Hospital).filter(models.Hospital.id == hospital_id).first()

    if labeled_count >= MIN_RECORDS_FOR_TRAINING:
        status_value = "ready_for_training"
    elif count >= MIN_RECORDS_FOR_TRAINING:
        # Enough data, not enough labels — a distinct, actionable state, and
        # the one most likely to bite a hospital mid-demo.
        status_value = "awaiting_labels"
    else:
        status_value = "collecting_data"

    return {
        "records_available": count,
        "labeled_records": labeled_count,
        "unlabeled_records": count - labeled_count,
        "label_coverage": round(labeled_count / count, 4) if count else 0.0,
        "requires_label": bool(hospital.requires_label) if hospital else False,
        "status": status_value,
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
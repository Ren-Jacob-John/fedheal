"""
Module 1 — Authentication & Multi-Tenancy

Run: uvicorn main:app --reload --port 8001
Docs: http://localhost:8001/docs

This is the foundation module: every other service (validation, training,
dashboard) should treat "which hospital does this request belong to" as
answered by this service's JWT, never by a client-supplied field.
"""
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
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


# ---------- Schemas ----------

class HospitalCreate(BaseModel):
    name: str


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


# ---------- Example of a hospital-scoped endpoint ----------
# Every future domain endpoint (vitals upload, training status, model version
# history) should follow this exact pattern: pull hospital_id from the JWT via
# get_current_user, never trust a hospital_id passed in the request body/query.

FAKE_TRAINING_STATUS_DB = {}  # hospital_id -> status dict, stand-in until Module 3 is wired in


@app.get("/training-status")
def get_training_status(current_user: models.User = Depends(get_current_user)):
    if current_user.role == models.Role.SUPER_ADMIN:
        return FAKE_TRAINING_STATUS_DB  # admin can see all hospitals
    return FAKE_TRAINING_STATUS_DB.get(
        current_user.hospital_id,
        {"round": 0, "status": "not started", "last_sync": None},
    )

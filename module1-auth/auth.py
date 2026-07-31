"""
Password hashing + JWT issuing/verification.

IMPORTANT: SECRET_KEY below is a placeholder for local dev only.
Before anything touches real hospital data, move this to an environment
variable / secrets manager and rotate it.
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException
from jose import jwt, JWTError
from passlib.context import CryptContext

SECRET_KEY = os.environ.get("FEDMED_JWT_SECRET", "dev-only-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Same shared-secret pattern Module 7 uses for its service-to-service
# endpoints (see module7-admin/auth.py's docstring for the reasoning) —
# this is what gates Module 3's real-data loader reading a hospital's
# stored vitals via GET /vitals/export. Not a substitute for real
# service auth (mTLS / per-service keys) before this touches real data.
SERVICE_KEY = os.environ.get("FEDMED_SERVICE_KEY", "dev-only-internal-service-key")


def require_service_key(x_service_key: str | None = Header(default=None)) -> None:
    if x_service_key != SERVICE_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid service key")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

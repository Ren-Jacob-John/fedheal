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

# Per-caller service keys, not one secret shared across every internal
# caller. Previously every service (Module 2, Module 3, Module 7) read
# and sent the SAME FEDMED_SERVICE_KEY, which meant compromising any one
# of them handed over the key to every service-to-service endpoint in the
# platform. The only real caller of Module 1's /vitals/export is Module
# 3's real_data.py, so it gets its own key — still a placeholder for real
# service auth (mTLS / a secrets manager) before this touches real data,
# but no longer a single point of compromise across unrelated services.
MODULE3_SERVICE_KEY = os.environ.get("FEDHEAL_SVC_KEY_M3_M1", "dev-only-key-module3-to-module1")


def require_module3_service_key(x_service_key: str | None = Header(default=None)) -> None:
    if x_service_key != MODULE3_SERVICE_KEY:
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

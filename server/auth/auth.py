"""
Password hashing + JWT issuing/verification, plus the scoped service
credentials Module 1 accepts from (and issues to) other FedHeal services.

Secrets come from config.py: real values are REQUIRED in staging/production
(startup fails without them); development/test fall back to clearly-labelled
dev-only values so local work needs no setup.
"""
from datetime import datetime, timedelta, timezone

from fastapi import Header
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
from passlib.context import CryptContext

import config
import service_auth

SECRET_KEY = config.get_secret("FEDMED_JWT_SECRET", dev_default="dev-only-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# --- Service credentials -------------------------------------------------
# One signing key per hop (never one secret shared by every internal caller):
#   M3 -> M1  Module 3 reading a hospital's validated vitals / the directory
#   M1 -> M2  Module 1 forwarding an upload for validation
# Module 1 VERIFIES the first and MINTS the second. See service_auth.py for
# the claim set (caller, audience, hospital scope) and the 401/403 rules.
M3_M1_SIGNING_KEY = config.get_secret(
    "FEDHEAL_SVC_SIGNING_KEY_M3_M1",
    dev_default="dev-only-signing-key-module3-to-module1",
)
M1_M2_SIGNING_KEY = config.get_secret(
    "FEDHEAL_SVC_SIGNING_KEY_M1_M2",
    dev_default="dev-only-signing-key-module1-to-module2",
)
# Retired: one static key that unlocked /vitals/export for EVERY hospital.
config.warn_if_set("FEDHEAL_SVC_KEY_M3_M1", "FEDHEAL_SVC_SIGNING_KEY_M3_M1 (hospital-scoped tokens)")

M3_CALLERS = frozenset({"module3"})


def require_export_credential(x_service_key: str | None = Header(default=None)) -> dict:
    """
    Authenticates a caller of GET /vitals/export. Returns the verified
    claims; the endpoint must still compare claims['hid'] with the hospital
    being requested (this dependency cannot see the query parameter's value
    in a way that keeps 401 ahead of 422).
    """
    return service_auth.verify_service_token(
        x_service_key,
        signing_key=M3_M1_SIGNING_KEY,
        allowed_audiences={service_auth.AUD_VITALS_EXPORT},
        allowed_callers=M3_CALLERS,
    )


def verify_directory_credential(token: str | None) -> dict:
    """Authenticates a caller of GET /hospitals with a service credential.
    A hospital-scoped export token is also accepted here, but only ever
    reveals that one hospital."""
    return service_auth.verify_service_token(
        token,
        signing_key=M3_M1_SIGNING_KEY,
        allowed_audiences={service_auth.AUD_HOSPITAL_DIRECTORY, service_auth.AUD_VITALS_EXPORT},
        allowed_callers=M3_CALLERS,
    )


def mint_validation_token(hospital_id: str) -> str:
    """Short-lived credential for ONE upload's call to Module 2, scoped to
    the uploader's hospital (taken from their JWT, never from the request)."""
    return service_auth.mint_service_token(
        M1_M2_SIGNING_KEY,
        caller="module1",
        audience=service_auth.AUD_VALIDATE,
        hospital_id=hospital_id,
        ttl_seconds=60,
    )


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


def inspect_access_token(token: str) -> tuple[dict | None, str | None]:
    """Like decode_access_token, but says WHY a token was rejected
    ("expired" | "invalid") so the audit log can tell them apart."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]), None
    except ExpiredSignatureError:
        return None, "expired"
    except JWTError:
        return None, "invalid"

"""
Two separate trust boundaries, on purpose:

1. Human/browser calls (viewing the overview, activating a hospital,
   triggering a round) — gated by the SAME JWT Module 1 issues. This
   service must be started with the identical FEDMED_JWT_SECRET Module 1
   uses, or every token will fail to decode here. That's intentional:
   there is exactly one login system in this platform (Module 1's), and
   every other service just verifies its tokens rather than growing a
   second one.

2. Service-to-service calls (Module 2 posting a validation-flag summary,
   Module 3 posting a completed round) — these aren't a logged-in human,
   so they don't have a user JWT. They're gated by a much simpler shared
   secret header instead. This is a placeholder for real service auth
   (mTLS between internal services, or per-service API keys issued by an
   internal secrets manager) — good enough for "only our own services can
   write to this table" at prototype stage, not a substitute for that
   later.
"""
import os

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

SECRET_KEY = os.environ.get("FEDMED_JWT_SECRET", "dev-only-change-me")
ALGORITHM = "HS256"
SERVICE_KEY = os.environ.get("FEDMED_SERVICE_KEY", "dev-only-internal-service-key")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="http://localhost:8001/token", auto_error=False)


def require_super_admin(token: str | None = Depends(oauth2_scheme)) -> dict:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise unauthorized
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise unauthorized

    if payload.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Requires super_admin role")
    return payload


def require_service_key(x_service_key: str | None = Header(default=None)) -> None:
    if x_service_key != SERVICE_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid service key")

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
   so they don't have a user JWT. They're gated by a per-caller shared
   secret header instead — Module 2 and Module 3 each get their OWN key
   (FEDHEAL_SVC_KEY_M2_M7 / FEDHEAL_SVC_KEY_M3_M7) rather than one secret
   shared across every internal caller, so a leaked/rotated key for one
   caller doesn't also grant access on the other's behalf. Still a
   placeholder for real service auth (mTLS between internal services, or
   per-service API keys issued by an internal secrets manager) — good
   enough for "only our own services can write to this table" at
   prototype stage, not a substitute for that later.
"""
import os

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

SECRET_KEY = os.environ.get("FEDMED_JWT_SECRET", "dev-only-change-me")
ALGORITHM = "HS256"
MODULE2_SERVICE_KEY = os.environ.get("FEDHEAL_SVC_KEY_M2_M7", "dev-only-key-module2-to-module7")
MODULE3_SERVICE_KEY = os.environ.get("FEDHEAL_SVC_KEY_M3_M7", "dev-only-key-module3-to-module7")

# Same cookie name Module 1 sets on login — browsers send cookies by host,
# not by port, so the dashboard's session cookie (set by Module 1 on :8001)
# reaches this service on :8005 too, as long as both are same-site.
TOKEN_COOKIE_NAME = "fedheal_token"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="http://localhost:8001/token", auto_error=False)


def require_super_admin(request: Request, token: str | None = Depends(oauth2_scheme)) -> dict:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = token or request.cookies.get(TOKEN_COOKIE_NAME)
    if token is None:
        raise unauthorized
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise unauthorized

    if payload.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Requires super_admin role")
    return payload


def require_module2_service_key(x_service_key: str | None = Header(default=None)) -> None:
    if x_service_key != MODULE2_SERVICE_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid service key")


def require_module3_service_key(x_service_key: str | None = Header(default=None)) -> None:
    if x_service_key != MODULE3_SERVICE_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid service key")

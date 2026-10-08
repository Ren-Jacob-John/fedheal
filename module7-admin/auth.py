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
import hmac

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

import config
import service_auth
from audit import audit_event

# Real values are REQUIRED in staging/production (startup fails otherwise);
# development/test fall back to dev-only values. See config.py.
SECRET_KEY = config.get_secret("FEDMED_JWT_SECRET", dev_default="dev-only-change-me")
ALGORITHM = "HS256"
# One signing key PER HOP. Callers present short-lived signed tokens (service_auth.py) that say who
# they are, which endpoint family they are for, and which hospital they may act for.
M2_M7_SIGNING_KEY = config.get_secret("FEDHEAL_SVC_SIGNING_KEY_M2_M7", dev_default="dev-only-signing-key-module2-to-module7")
M3_M7_SIGNING_KEY = config.get_secret("FEDHEAL_SVC_SIGNING_KEY_M3_M7", dev_default="dev-only-signing-key-module3-to-module7")
M8_M7_SIGNING_KEY = config.get_secret("FEDHEAL_SVC_SIGNING_KEY_M8_M7", dev_default="dev-only-signing-key-module8-to-module7")
config.warn_if_set("FEDHEAL_SVC_KEY_M2_M7", "FEDHEAL_SVC_SIGNING_KEY_M2_M7 (hospital-scoped tokens)")
config.warn_if_set("FEDHEAL_SVC_KEY_M3_M7", "FEDHEAL_SVC_SIGNING_KEY_M3_M7 (scoped tokens)")

# Same cookie name Module 1 sets on login — browsers send cookies by host,
# not by port, so the dashboard's session cookie (set by Module 1 on :8001)
# reaches this service on :8005 too, as long as both are same-site.
TOKEN_COOKIE_NAME = "fedheal_token"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="http://localhost:8001/token", auto_error=False)


def get_raw_token(request: Request, token: str | None = Depends(oauth2_scheme)) -> str | None:
    """The caller's Bearer token, or — for the browser dashboard, which
    authenticates by httpOnly cookie — the cookie's value. Used when this
    service forwards the caller's own credential to Module 1: passing only
    the Bearer header (None for cookie sessions) made those forwards go out
    as "Bearer None"."""
    return token or request.cookies.get(TOKEN_COOKIE_NAME)


def require_super_admin(request: Request, token: str | None = Depends(oauth2_scheme)) -> dict:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = token or request.cookies.get(TOKEN_COOKIE_NAME)
    if token is None:
        audit_event("authn.failure", "denied", request=request, reason="missing_credentials",
                    level=20)
        raise unauthorized
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        audit_event("authn.failure", "denied", request=request, reason="invalid_or_expired_token")
        raise unauthorized

    if payload.get("role") != "super_admin":
        audit_event("authz.denied", "denied", request=request, actor_user_id=payload.get("sub"),
                    actor_role=payload.get("role"), hospital_id=payload.get("hospital_id"),
                    required_roles="super_admin")
        raise HTTPException(status_code=403, detail="Requires super_admin role")
    return payload


def _verify_hop(request: Request, presented: str | None, *, key: str, audiences, callers, caller: str) -> dict:
    try:
        return service_auth.verify_service_token(presented, signing_key=key, allowed_audiences=audiences,
                                                 allowed_callers=callers)
    except HTTPException as e:
        audit_event("service_authn.failure", "denied", request=request, actor_service=caller,
                    reason="invalid_service_credential" if e.status_code == 401 else "wrong_audience_or_caller")
        raise


def require_flag_report(request: Request, x_service_key: str | None = Header(default=None)) -> dict:
    """M2 -> M7 flag summary. Returns verified claims; the route must check hid == the hospital in the body."""
    return _verify_hop(request, x_service_key, key=M2_M7_SIGNING_KEY, caller="module2",
                       audiences={service_auth.AUD_FLAG_REPORT}, callers={"module2"})


def require_round_report(request: Request, x_service_key: str | None = Header(default=None)) -> dict:
    return _verify_hop(request, x_service_key, key=M3_M7_SIGNING_KEY, caller="module3",
                       audiences={service_auth.AUD_ROUND_REPORT}, callers={"module3"})


def require_model_candidate_credential(request: Request, x_service_key: str | None = Header(default=None)) -> dict:
    return _verify_hop(request, x_service_key, key=M3_M7_SIGNING_KEY, caller="module3",
                       audiences={service_auth.AUD_MODEL_CANDIDATE}, callers={"module3"})


def require_promoted_model_read(request: Request, x_service_key: str | None = Header(default=None)) -> dict:
    return _verify_hop(request, x_service_key, key=M8_M7_SIGNING_KEY, caller="module8",
                       audiences={service_auth.AUD_PROMOTED_MODEL}, callers={"module8"})

"""
Verifies the same JWT Module 1 issues — this service never issues or
stores credentials of its own, same pattern as Module 7's auth.py.

Unlike Module 7's `require_super_admin`, running a synthesis is something
ANY logged-in hospital user does for a case in front of them, not an
admin/operator action — so this only checks "is this a valid FedHeal
session", not a specific role. It still means an unauthenticated caller
can't run arbitrary model inference through this service for free, and
every request is attributable to a real user if this ever needs an audit
trail (e.g. "who ran a synthesis on this case, and when").
"""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError

import config
from audit import audit_event

# Required in staging/production (startup fails otherwise); dev/test fall
# back to a dev-only value. See config.py.
SECRET_KEY = config.get_secret("FEDMED_JWT_SECRET", dev_default="dev-only-change-me")
ALGORITHM = "HS256"

# Same cookie name Module 1 sets on login — browsers send cookies by host,
# not by port, so the dashboard's session cookie reaches this service too,
# as long as both are same-site (see module7-admin/auth.py for the same
# pattern, already in production use there).
TOKEN_COOKIE_NAME = "fedheal_token"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="http://localhost:8001/token", auto_error=False)


def require_authenticated_user(request: Request, token: str | None = Depends(oauth2_scheme)) -> dict:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = token or request.cookies.get(TOKEN_COOKIE_NAME)
    if token is None:
        audit_event("authn.failure", "denied", request=request, reason="missing_credentials", level=20)
        raise unauthorized
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        audit_event("authn.failure", "denied", request=request, reason="invalid_or_expired_token")
        raise unauthorized
    return payload


def get_raw_token(request: Request, token: str | None = Depends(oauth2_scheme)) -> str | None:
    """The caller's own token (Bearer header, or the dashboard's httpOnly
    cookie). Module 8 forwards it to Module 1 to read a record: record
    access is decided by the user's own tenant, and this service holds no
    credential of its own for it."""
    return token or request.cookies.get(TOKEN_COOKIE_NAME)

"""
Service-to-service credentials that can express WHO is calling and WHICH
HOSPITAL they may act for.

CANONICAL COPY: duplicated verbatim into module1-auth, module2-validation
and module3-fedlearning (see config.py's note; tests/test_shared_files_in_sync.py
enforces it).

Why this exists
---------------
Every internal call used to be authenticated by a static shared string in
the `X-Service-Key` header. That proves "the caller knows the string", but a
string cannot say "...and only for hospital A". For /vitals/export the
consequence was that Module 3's one key unlocked every hospital, with the
hospital picked by a query parameter the caller controls.

This is NOT a second login system. It is the same header (`X-Service-Key`)
and the same JWT library Module 1 already uses for users (python-jose,
HS256), carrying a signed claim set instead of a bare string:

    iss  "fedheal-service"                  (fixed)
    sub  calling service, e.g. "module3"    (WHO)
    aud  the endpoint family it is for      (WHAT)
    hid  hospital id it may act for, or "*" (WHICH TENANT)
    exp  expiry (required), iat, jti

Each hop has its OWN signing key (e.g. FEDHEAL_SVC_SIGNING_KEY_M3_M1), so a
key for one hop is useless on another, and user JWTs (signed with
FEDMED_JWT_SECRET) can never be replayed here or vice versa.

Failure semantics used by every verifier in the platform:
    missing / malformed / bad signature / expired  -> 401
    valid signature but wrong caller or audience   -> 403
    valid but scoped to a different hospital       -> 403 (checked by caller)
"""
import time
import uuid

from fastapi import HTTPException
from jose import JWTError, jwt

ISSUER = "fedheal-service"
ALGORITHM = "HS256"
ANY_HOSPITAL = "*"

# Audiences (endpoint families)
AUD_VITALS_EXPORT = "module1:vitals-export"
AUD_HOSPITAL_DIRECTORY = "module1:hospital-directory"
AUD_VALIDATE = "module2:validate"


def mint_service_token(
    signing_key: str,
    *,
    caller: str,
    audience: str,
    hospital_id: str | None = None,
    ttl_seconds: int = 300,
) -> str:
    """Mint a scoped service token. `hospital_id` may be ANY_HOSPITAL only
    for AUD_HOSPITAL_DIRECTORY (listing); export/validate tokens must name
    exactly one hospital."""
    if hospital_id == ANY_HOSPITAL and audience != AUD_HOSPITAL_DIRECTORY:
        raise ValueError("a wildcard hospital scope is only valid for the hospital directory")
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": caller,
        "aud": audience,
        "iat": now,
        "exp": now + int(ttl_seconds),
        "jti": uuid.uuid4().hex,
    }
    if hospital_id is not None:
        claims["hid"] = hospital_id
    return jwt.encode(claims, signing_key, algorithm=ALGORITHM)


def verify_service_token(
    token: str | None,
    *,
    signing_key: str,
    allowed_audiences: set[str] | frozenset[str],
    allowed_callers: set[str] | frozenset[str],
) -> dict:
    """Returns the verified claims, or raises HTTPException 401 / 403."""
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid service credential")
    try:
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=[ALGORITHM],
            # aud is compared manually below so a correctly-signed token for
            # the WRONG endpoint is a 403 (authenticated, not authorised),
            # not indistinguishable from a forged one.
            options={"verify_aud": False, "require_exp": True, "require_iat": True},
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Missing or invalid service credential")
    if claims.get("iss") != ISSUER:
        raise HTTPException(status_code=401, detail="Missing or invalid service credential")
    if claims.get("aud") not in allowed_audiences or claims.get("sub") not in allowed_callers:
        raise HTTPException(status_code=403, detail="Service is not permitted to call this endpoint")
    return claims


def hospital_scope(claims: dict) -> str | None:
    """The hospital id a verified token is scoped to (or ANY_HOSPITAL), if any."""
    hid = claims.get("hid")
    return hid if isinstance(hid, str) and hid else None

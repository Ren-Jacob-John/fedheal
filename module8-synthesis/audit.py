"""
Structured audit logging for security-relevant actions.

CANONICAL COPY: duplicated verbatim into module1-auth, module2-validation,
module7-admin and module8-synthesis (see config.py's note).

One JSON object per line on the `fedheal.audit` logger. Fields are an
ALLOWLIST — anything not named below is dropped, so a careless call site
cannot leak a password, JWT, API key, e-mail address or patient record into
the log. Values are limited to short strings, ints, floats and bools.

Safe identifiers only: user id, role, hospital id, calling service name,
endpoint (route template, never the query string), action, outcome,
timestamp, and coarse counts.
"""
import hashlib
import json
import logging
import re
import sys
from datetime import datetime, timezone

logger = logging.getLogger("fedheal.audit")

if not logger.handlers and not logging.getLogger().handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)

# Extra keys a call site may attach. Deliberately small.
_ALLOWED_EXTRA = frozenset({
    "reason", "decision", "record_id", "target_user_id", "target_role",
    "target_hospital_id", "requested_hospital_id", "token_hospital_id",
    "caller", "count", "total", "passed", "flagged", "rejected", "stored",
    "is_active", "requires_label", "status_code", "required_roles",
    "username_hash", "round_number",
})

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_MAX_STR = 96


def hash_identifier(value: str) -> str:
    """Short, non-reversible tag for correlating repeated attempts on the
    same login name without ever writing the name itself to a log."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:12]


def _clean(value):
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return _CONTROL_CHARS.sub("?", value)[:_MAX_STR]
    return None  # lists/dicts/objects are never logged


def _endpoint(request) -> str | None:
    if request is None:
        return None
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    return template or request.url.path


def _client_ip(request) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def audit_event(
    action: str,
    outcome: str,
    *,
    request=None,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
    actor_service: str | None = None,
    hospital_id: str | None = None,
    level: int | None = None,
    **extra,
) -> dict:
    """
    action:  dotted verb, e.g. "hospital.create", "vitals.export", "authn.failure"
    outcome: "success" | "failure" | "denied"
    Returns the event dict (handy for tests); it has already been logged.
    """
    event = {
        "event": "audit",
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "action": action,
        "outcome": outcome,
        "actor_user_id": _clean(actor_user_id),
        "actor_role": _clean(getattr(actor_role, "value", actor_role)),
        "actor_service": _clean(actor_service),
        "hospital_id": _clean(hospital_id),
        "method": request.method if request is not None else None,
        "endpoint": _endpoint(request),
        "client_ip": _client_ip(request),
    }
    for key, value in extra.items():
        if key in _ALLOWED_EXTRA:
            cleaned = _clean(getattr(value, "value", value))
            if cleaned is not None:
                event[key] = cleaned
    event = {k: v for k, v in event.items() if v is not None}
    if level is None:
        level = logging.INFO if outcome == "success" else logging.WARNING
    logger.log(level, json.dumps(event, sort_keys=True, separators=(",", ":")))
    return event

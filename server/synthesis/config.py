"""
Environment + secret handling shared by every FedHeal service.

CANONICAL COPY: this file is duplicated verbatim into each service folder
(module1-auth, module2-validation, module3-fedlearning, module7-admin,
module8-synthesis) because each module is deployed on its own with its own
requirements.txt. tests/test_shared_files_in_sync.py fails if the copies
drift apart — edit one, then copy it to the others.

Environment model
-----------------
FEDHEAL_ENV selects the deployment tier:

    development | test   local work only. Missing secrets fall back to
                         clearly-labelled dev-only values (with a warning
                         that names the variable, never the value).
    staging | production Missing/placeholder/short secrets are a startup
                         error. Nothing falls back.

If FEDHEAL_ENV is NOT set, it is treated as **production**. Failing closed
is deliberate: a deployment that forgets to set it must not silently run on
development secrets. Local developers set FEDHEAL_ENV=development (it is in
every .env.example).

Nothing in this module ever logs or returns a secret value in an error.
"""
import logging
import os

try:  # python-dotenv is a dependency of most services, but not of every script
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

logger = logging.getLogger("fedheal.config")

LOCAL_ENVS = ("development", "test")
VALID_ENVS = LOCAL_ENVS + ("staging", "production")

MIN_SECRET_LENGTH = 32

# Substrings that mark a value as an example/placeholder rather than a real
# secret. Rejected outside local environments.
_PLACEHOLDER_MARKERS = (
    "change-me", "changeme", "dev-only", "realkeyvalue", "your-", "example",
    "placeholder", "iamgod", "iammighty", "password", "secret-key", "todo",
)


class ConfigError(RuntimeError):
    """Raised at startup when required configuration is missing or unsafe."""


def current_env() -> str:
    value = os.environ.get("FEDHEAL_ENV", "production").strip().lower()
    if value not in VALID_ENVS:
        raise ConfigError(
            f"FEDHEAL_ENV must be one of {', '.join(VALID_ENVS)} (got an unrecognised value)"
        )
    return value


def is_local() -> bool:
    return current_env() in LOCAL_ENVS


_warned: set[str] = set()


def _warn_dev_fallback(name: str) -> None:
    if name in _warned:
        return
    _warned.add(name)
    logger.warning(
        "%s is not set; using a DEVELOPMENT-ONLY fallback because FEDHEAL_ENV=%s. "
        "This is refused in staging/production.",
        name, current_env(),
    )


def _check_strength(name: str, value: str, min_len: int) -> None:
    lowered = value.lower()
    if len(value) < min_len:
        raise ConfigError(f"{name} is too short (minimum {min_len} characters) for FEDHEAL_ENV={current_env()}")
    if any(marker in lowered for marker in _PLACEHOLDER_MARKERS):
        raise ConfigError(f"{name} looks like a placeholder/example value; set a real random secret")


def get_secret(name: str, *, dev_default: str | None, min_len: int = MIN_SECRET_LENGTH) -> str:
    """
    Required secret. Local: env value, else `dev_default` (warned). Staging /
    production: env value only, and it must be long enough and not a
    placeholder — otherwise startup fails.
    """
    value = os.environ.get(name, "").strip()
    if is_local():
        if value:
            return value
        if dev_default is None:
            raise ConfigError(f"{name} must be set (no development fallback exists for it)")
        _warn_dev_fallback(name)
        return dev_default
    if not value:
        raise ConfigError(f"{name} must be set when FEDHEAL_ENV={current_env()}")
    _check_strength(name, value, min_len)
    return value


def get_optional_secret(name: str, *, dev_default: str | None = None,
                        min_len: int = MIN_SECRET_LENGTH) -> str | None:
    """
    A secret only SOME processes of a service hold (e.g. a hospital's own
    client holds a pre-minted token, not the signing key). Unset -> None in
    staging/production. If set, it is strength-checked outside local envs.
    """
    value = os.environ.get(name, "").strip()
    if value:
        if not is_local():
            _check_strength(name, value, min_len)
        return value
    if is_local() and dev_default is not None:
        _warn_dev_fallback(name)
        return dev_default
    return None


def warn_if_set(name: str, replacement: str) -> None:
    """Migration aid: a retired variable is still present in the environment."""
    if os.environ.get(name):
        logger.warning("%s is no longer used and is IGNORED; it was replaced by %s.", name, replacement)


def env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer")
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    return value


def cookie_secure() -> bool:
    """
    Session-cookie `Secure` flag. Local: FEDHEAL_COOKIE_SECURE (default
    false, so plain-http dev works). Staging/production: always true; an
    explicit false is a startup error rather than being silently honoured.
    """
    raw = os.environ.get("FEDHEAL_COOKIE_SECURE")
    if is_local():
        return (raw or "false").strip().lower() == "true"
    if raw is not None and raw.strip().lower() == "false":
        raise ConfigError("FEDHEAL_COOKIE_SECURE=false is not allowed outside development/test")
    return True


DEFAULT_DEV_ORIGIN = "http://localhost:5173"


def cors_settings(*, methods: tuple[str, ...], headers: tuple[str, ...] = ("Authorization", "Content-Type")) -> dict:
    """
    kwargs for CORSMiddleware. Origins come from FEDHEAL_DASHBOARD_ORIGIN
    (comma-separated). `*` is never accepted (this API uses cookie
    credentials, and a wildcard is meaningless/unsafe with them). Local
    envs default to the Vite dev server; staging/production must set the
    variable explicitly and every origin must be https.

    Methods/headers are passed by each service — only what its browser
    callers actually use (the dashboard sends Authorization + Content-Type).
    """
    raw = os.environ.get("FEDHEAL_DASHBOARD_ORIGIN", "").strip()
    if not raw:
        if not is_local():
            raise ConfigError(f"FEDHEAL_DASHBOARD_ORIGIN must be set when FEDHEAL_ENV={current_env()}")
        raw = DEFAULT_DEV_ORIGIN
    origins = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    if not origins:
        raise ConfigError("FEDHEAL_DASHBOARD_ORIGIN contains no origins")
    for origin in origins:
        if origin == "*" or "*" in origin:
            raise ConfigError("FEDHEAL_DASHBOARD_ORIGIN must list explicit origins; wildcards are not allowed")
        if not is_local() and not origin.startswith("https://"):
            raise ConfigError("FEDHEAL_DASHBOARD_ORIGIN origins must be https:// outside development/test")
    return {
        "allow_origins": origins,
        "allow_credentials": True,
        "allow_methods": list(methods),
        "allow_headers": list(headers),
    }

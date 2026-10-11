"""
Shared helpers for the Module 1 security tests (test_security.py,
test_uploads.py). Builds the app against the in-memory document store, exactly
like test_auth.py does, and offers small factories for hospitals, users,
tokens and vitals rows.
"""
import os
import uuid

os.environ.setdefault("FEDHEAL_DB_BACKEND", "memory")  # conftest.py normally selects the shared file store
os.environ.setdefault("FEDHEAL_ALLOW_PUBLIC_REGISTRATION", "true")  # the open path is under test; closed-by-default is tested in test_cases.py

import database  # noqa: E402
import models  # noqa: E402

import main  # noqa: E402
import service_auth  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402

client = TestClient(main.app)

DEFAULT_ORIGIN = "http://localhost:5173"


def uid(label: str = "x") -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_hospital_row(name: str | None = None, requires_label: bool = False) -> str:
    """Creates a hospital directly through the repository; returns its id."""
    return database.repo.create_hospital(models.Hospital(name=name or uid("Hospital"),
                                                         requires_label=requires_label)).id


def make_user(role: models.Role, hospital_id: str | None = None, password: str = "pw12345-test") -> tuple[str, str]:
    """Creates a user through the repository; returns (user_id, valid JWT)."""
    u = database.repo.create_user(models.User(
        email=f"{uid(role.value)}@test.fedheal.local",
        hashed_password=main.auth.hash_password(password),
        role=role,
        hospital_id=hospital_id,
    ))
    token = main.auth.create_access_token({"sub": u.id, "hospital_id": u.hospital_id, "role": u.role.value})
    return u.id, token


def user_token(user_id: str, role: models.Role, hospital_id: str | None, *, expires_minutes: int = 60,
               secret: str | None = None) -> str:
    """A JWT for an existing user with control over expiry / signing key."""
    data = {"sub": user_id, "hospital_id": hospital_id, "role": role.value}
    if secret is None:
        return main.auth.create_access_token(data, expires_minutes=expires_minutes)
    from datetime import datetime, timedelta, timezone

    data["exp"] = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    return jwt.encode(data, secret, algorithm="HS256")


def add_vitals(hospital_id: str, n: int = 3, *, status: str = "passed", labeled: bool = True) -> list[str]:
    """Inserts n vitals rows for a hospital; returns their patient_refs."""
    refs, rows = [], []
    for i in range(n):
        ref = f"{hospital_id[:8]}-P{i}-{uuid.uuid4().hex[:6]}"
        refs.append(ref)
        rows.append(models.VitalsRecord(
            hospital_id=hospital_id, patient_ref=ref, age_years=50, height_cm=170, weight_kg=70,
            systolic_bp=120, diastolic_bp=80, heart_rate_bpm=70, medication_count=0,
            medication_mg_total=0, label=(i % 2) if labeled else None,
            label_source="hospital" if labeled else "missing", validation_status=status,
        ))
    database.repo.add_vitals_bulk(rows)
    return refs


def add_flagged_record(hospital_id: str) -> str:
    """Inserts one flagged vitals row; returns its record id."""
    return database.repo.add_vitals(models.VitalsRecord(
        hospital_id=hospital_id, patient_ref=uid("flag"), age_years=50, height_cm=170, weight_kg=70,
        medication_count=0, medication_mg_total=0, label=None, label_source="missing",
        validation_status="flagged",
    )).id


def record_exists(record_id: str) -> bool:
    return database.repo.get_vitals(record_id) is not None


def record_status(record_id: str) -> str | None:
    r = database.repo.get_vitals(record_id)
    return r.validation_status if r else None


def hospital_count() -> int:
    return len(database.repo.list_hospitals())


def svc_token(hospital_id: str | None, *, audience: str = service_auth.AUD_VITALS_EXPORT,
              caller: str = "module3", key: str | None = None, ttl: int = 300) -> str:
    """A Module 3 -> Module 1 service token. Signed with the real signing
    key by default; pass `key` to forge one."""
    import time

    now = int(time.time())
    claims = {"iss": service_auth.ISSUER, "sub": caller, "aud": audience, "iat": now, "exp": now + ttl,
              "jti": uuid.uuid4().hex}
    if hospital_id is not None:
        claims["hid"] = hospital_id
    return jwt.encode(claims, key or main.auth.M3_M1_SIGNING_KEY, algorithm="HS256")

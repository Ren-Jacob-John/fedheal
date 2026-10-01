"""
Module 2 — Data Ingestion & Validation

Run: uvicorn main:app --reload --port 8002
Docs: http://localhost:8002/docs

Pipeline for every batch upload, in order:
  1. De-identification screen (hard reject if a forbidden field is present)
  2. Schema validation (correct fields/types — pydantic)
  3. Plausibility range checks (hard reject)
  4. Cross-field consistency checks (hard reject)
  4b. Required-outcome-label check, ONLY when the caller sets
      require_label=true (hard reject) — see rules.check_required_label
  5. Isolation-forest outlier flag across the batch (soft flag, not rejection)

Only records that pass 1-4 are eligible to reach Module 3's local training —
flagged-but-passing records (step 5) go to the hospital dashboard for human
review rather than silently being dropped or silently being trained on.
"""
import io
import math
import os
from collections import Counter
from typing import Literal, Optional

import httpx
import pandas as pd
from fastapi import Depends, FastAPI, UploadFile, File, Form, HTTPException, Header, Request
from pydantic import BaseModel, ValidationError

import config
import limits
import service_auth
from audit import audit_event
from anomaly import flag_outliers
from rules import (
    check_forbidden_fields,
    check_plausible_ranges,
    check_cross_field_consistency,
    check_required_label,
)
from schema import VitalsRecord
from docs_theme import mount_custom_docs

app = FastAPI(title="FedHeal Data Validation Service", version="0.1.0", docs_url=None)
mount_custom_docs(app, accent="#1f9d63", accent_soft="#dcf5e8")  # green — Module 2

# Module 7 (Admin/Platform) integration — best-effort only. If the admin
# service isn't running, validation still works exactly as before; we just
# have nowhere to report the flag summary to. This is a rolled-up COUNT per
# reason string, never a raw record, matching the "operator can see flags,
# never patient data" design.
ADMIN_API_URL = os.environ.get("FEDHEAL_ADMIN_API_URL", "http://localhost:8005")
# Module 2 -> Module 7 flag reports (outbound). Required in staging/production.
ADMIN_SERVICE_KEY = config.get_secret("FEDHEAL_SVC_KEY_M2_M7", dev_default="dev-only-key-module2-to-module7")

# ---- Inbound access control ------------------------------------------------
# This service is INTERNAL: the browser talks to Module 1, and Module 1
# forwards uploads here. Every /validate/* call must carry a service
# credential minted by Module 1 for the uploading hospital (see
# service_auth.py). Verification key is shared with Module 1 only.
VALIDATE_SIGNING_KEY = config.get_secret(
    "FEDHEAL_SVC_SIGNING_KEY_M1_M2",
    dev_default="dev-only-signing-key-module1-to-module2",
)
VALIDATE_CALLERS = frozenset({"module1"})

UPLOAD_LIMITS = limits.UploadLimits.from_env()
# Module 1 already enforces the same limits and adds a small wrapper around
# what it forwards, so this service allows slightly more than Module 1 does
# instead of rejecting something Module 1 legitimately accepted.
_JSON_LIMIT = UPLOAD_LIMITS.max_json_body_bytes + limits.MULTIPART_OVERHEAD_BYTES
_CSV_LIMIT = UPLOAD_LIMITS.max_csv_bytes + limits.MULTIPART_OVERHEAD_BYTES

app.add_middleware(
    limits.BodySizeLimitMiddleware,
    limits={"/validate/vitals": _JSON_LIMIT, "/validate/vitals/csv": _CSV_LIMIT},
)
# Browsers never call this service directly (Module 1 does, server-side), so
# no cross-origin browser access is granted at all — no CORS middleware.


def require_validation_credential(
    request: Request,
    x_service_key: str | None = Header(default=None),
) -> dict:
    """401: missing/forged/expired credential. 403: a valid credential for
    a different service or endpoint. Returns the verified claims."""
    try:
        return service_auth.verify_service_token(
            x_service_key,
            signing_key=VALIDATE_SIGNING_KEY,
            allowed_audiences={service_auth.AUD_VALIDATE},
            allowed_callers=VALIDATE_CALLERS,
        )
    except HTTPException as exc:
        audit_event(
            "service_authn.failure", "denied", request=request,
            reason="invalid_credential" if exc.status_code == 401 else "service_not_permitted",
            status_code=exc.status_code,
        )
        raise


def resolve_tenant(request: Request, claims: dict, requested_hospital_id: str | None) -> str:
    """
    The hospital this validation belongs to comes from the credential. A
    caller-supplied hospital_id is accepted only if it matches (it exists for
    backwards compatibility); a mismatch is a 403 and an audit event, and a
    credential with no single-hospital scope is not accepted here at all.
    """
    token_hospital = service_auth.hospital_scope(claims)
    if not token_hospital or token_hospital == service_auth.ANY_HOSPITAL:
        audit_event("validate", "denied", request=request, actor_service=claims.get("sub"),
                    reason="credential_not_tenant_scoped")
        raise HTTPException(status_code=403, detail="Credential is not scoped to a hospital")
    if requested_hospital_id is not None and requested_hospital_id != token_hospital:
        audit_event("cross_tenant.attempt", "denied", request=request, actor_service=claims.get("sub"),
                    requested_hospital_id=requested_hospital_id, token_hospital_id=token_hospital)
        raise HTTPException(status_code=403, detail="Credential is not authorized for this hospital")
    return token_hospital


def report_flags_to_admin(hospital_id: str | None, results: list["ValidationResult"]) -> None:
    if not hospital_id:
        return  # no tenant to attribute this batch to — skip rather than guess
    tallies: Counter[tuple[str, str]] = Counter()
    for r in results:
        if r.status == "passed":
            continue
        for reason in r.reasons:
            tallies[(r.status, reason)] += 1
    for (status, reason), count in tallies.items():
        try:
            httpx.post(
                f"{ADMIN_API_URL}/admin/flags",
                json={"hospital_id": hospital_id, "status": status, "reason": reason, "count": count},
                headers={"X-Service-Key": ADMIN_SERVICE_KEY},
                timeout=2.0,
            )
        except httpx.HTTPError:
            pass  # admin dashboard is a nice-to-have view, not a dependency of validation itself


class ValidationResult(BaseModel):
    patient_ref: str | None
    status: Literal["passed", "flagged", "rejected"]
    reasons: list[str]


class BatchValidationRequest(BaseModel):
    records: list[dict]
    # Optional so this endpoint keeps working exactly as before for anyone
    # calling it without a tenant context. When present, flag/reject counts
    # get attributed to this hospital for Module 7's dashboard.
    hospital_id: str | None = None
    # Sprint A. Defaults False so every existing caller behaves exactly as
    # before; Module 1 sets it to True for hospitals flagged as label
    # suppliers. This service doesn't (and shouldn't) know which hospitals
    # those are — that's tenant configuration, and it lives in Module 1.
    require_label: bool = False


class BatchValidationResponse(BaseModel):
    total: int
    passed: int
    flagged: int
    rejected: int
    results: list[ValidationResult]


def _validate_records(
    raw_records: list[dict],
    hospital_id: str | None,
    require_label: bool = False,
) -> BatchValidationResponse:
    """
    The actual five-stage gate, shared by both the JSON endpoint and the
    CSV endpoint below — one implementation, two ways in, so CSV uploads
    get exactly the same checks JSON uploads always have, not a
    second-class parallel path.
    """
    results: list[ValidationResult] = []
    clean_indexed: dict[int, dict] = {}  # index -> record dict, for outlier pass

    for idx, raw in enumerate(raw_records):
        # 1. De-identification screen — checked on the RAW dict, before schema
        #    parsing, so we still catch it even if extra fields would
        #    otherwise be silently dropped by pydantic.
        forbidden = check_forbidden_fields(raw)
        if forbidden:
            results.append(ValidationResult(
                patient_ref=raw.get("patient_ref"),
                status="rejected",
                reasons=[f"contains identifying field(s): {', '.join(forbidden)}"],
            ))
            continue

        # 2. Schema validation
        try:
            record = VitalsRecord(**raw)
        except ValidationError as e:
            results.append(ValidationResult(
                patient_ref=raw.get("patient_ref"),
                status="rejected",
                reasons=[str(err["msg"]) + f" ({'.'.join(str(p) for p in err['loc'])})"
                         for err in e.errors()],
            ))
            continue

        # 3, 4 & 4b. Plausibility + cross-field consistency + (optionally)
        # the required-label check. Collected together so a record with
        # several problems reports all of them in one pass, rather than
        # making the uploader fix one, re-upload, and discover the next.
        reasons = check_plausible_ranges(record) + check_cross_field_consistency(record)
        if require_label:
            reasons += check_required_label(record)
        if reasons:
            results.append(ValidationResult(
                patient_ref=record.patient_ref, status="rejected", reasons=reasons
            ))
            continue

        # Passed the hard checks — eligible for the batch-level outlier pass.
        clean_indexed[idx] = record.model_dump()
        results.append(ValidationResult(patient_ref=record.patient_ref, status="passed", reasons=[]))

    # 5. Isolation-forest outlier flag, only over records that passed hard checks.
    if clean_indexed:
        indices = list(clean_indexed.keys())
        outlier_flags = flag_outliers([clean_indexed[i] for i in indices])
        for idx, is_outlier in zip(indices, outlier_flags):
            if is_outlier:
                results[idx].status = "flagged"
                results[idx].reasons = ["statistical outlier relative to this batch (isolation forest)"]

    passed = sum(1 for r in results if r.status == "passed")
    flagged = sum(1 for r in results if r.status == "flagged")
    rejected = sum(1 for r in results if r.status == "rejected")

    report_flags_to_admin(hospital_id, results)

    return BatchValidationResponse(
        total=len(results), passed=passed, flagged=flagged, rejected=rejected, results=results
    )


@app.post("/validate/vitals", response_model=BatchValidationResponse)
def validate_vitals_batch(
    payload: BatchValidationRequest,
    request: Request,
    claims: dict = Depends(require_validation_credential),
):
    hospital_id = resolve_tenant(request, claims, payload.hospital_id)
    limits.check_records(payload.records, UPLOAD_LIMITS)
    result = _validate_records(payload.records, hospital_id, payload.require_label)
    audit_event("validate", "success", request=request, actor_service=claims.get("sub"),
                hospital_id=hospital_id, total=result.total, passed=result.passed,
                flagged=result.flagged, rejected=result.rejected)
    return result


# CSV upload — most hospitals will export from their own EHR/spreadsheet
# systems as CSV, not hand-write JSON. Same five-stage gate as
# /validate/vitals; the only difference is the wire format going in.
# Expected columns match schema.VitalsRecord's field names exactly
# (patient_ref, age_years, height_cm, weight_kg, systolic_bp, diastolic_bp,
# heart_rate_bpm, medication_count, medication_mg_total, label). Missing
# optional columns are fine; missing required columns fail that row the
# same way a missing JSON field would.
@app.post("/validate/vitals/csv", response_model=BatchValidationResponse)
async def validate_vitals_csv(
    request: Request,
    file: UploadFile = File(...),
    hospital_id: Optional[str] = Form(None),
    require_label: bool = Form(False),
    claims: dict = Depends(require_validation_credential),
):
    tenant_id = resolve_tenant(request, claims, hospital_id)
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Expected a .csv file")

    raw_bytes = await file.read()
    if len(raw_bytes) > UPLOAD_LIMITS.max_csv_bytes:
        raise limits.too_large(f"CSV file too large (limit {UPLOAD_LIMITS.max_csv_bytes} bytes)")
    try:
        # nrows caps parsing work at one row past the limit, enough to detect "too many".
        df = pd.read_csv(io.BytesIO(raw_bytes), nrows=UPLOAD_LIMITS.max_records + 1)
    except Exception as e:  # pandas raises several different error types here
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")
    if len(df) > UPLOAD_LIMITS.max_records:
        raise limits.too_large(f"Too many records in one request (limit {UPLOAD_LIMITS.max_records})")
    if len(df.columns) > UPLOAD_LIMITS.max_record_fields:
        raise limits.too_large(f"CSV has too many columns (limit {UPLOAD_LIMITS.max_record_fields})")

    # NaN -> None so pydantic sees a missing optional field, not a float
    # NaN. df.where(df.notnull(), None) looks like it should do this but
    # doesn't for numeric columns — assigning None back into a float64
    # column just re-coerces to NaN. Doing it per-value after to_dict()
    # sidesteps the dtype coercion entirely.
    records = df.to_dict(orient="records")
    records = [
        {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in rec.items()}
        for rec in records
    ]
    limits.check_records(records, UPLOAD_LIMITS)
    result = _validate_records(records, tenant_id, require_label)
    audit_event("validate_csv", "success", request=request, actor_service=claims.get("sub"),
                hospital_id=tenant_id, total=result.total, passed=result.passed,
                flagged=result.flagged, rejected=result.rejected)
    return result


@app.get("/health")
def health():
    return {"status": "ok"}

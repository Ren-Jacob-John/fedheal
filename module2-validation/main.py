"""
Module 2 — Data Ingestion & Validation

Run: uvicorn main:app --reload --port 8002
Docs: http://localhost:8002/docs

Pipeline for every batch upload, in order:
  1. De-identification screen (hard reject if a forbidden field is present)
  2. Schema validation (correct fields/types — pydantic)
  3. Plausibility range checks (hard reject)
  4. Cross-field consistency checks (hard reject)
  5. Isolation-forest outlier flag across the batch (soft flag, not rejection)

Only records that pass 1-4 are eligible to reach Module 3's local training —
flagged-but-passing records (step 5) go to the hospital dashboard for human
review rather than silently being dropped or silently being trained on.
"""
import os
from collections import Counter
from typing import Literal

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, ValidationError

from anomaly import flag_outliers
from rules import check_forbidden_fields, check_plausible_ranges, check_cross_field_consistency
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
ADMIN_SERVICE_KEY = os.environ.get("FEDMED_SERVICE_KEY", "dev-only-internal-service-key")


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


class BatchValidationResponse(BaseModel):
    total: int
    passed: int
    flagged: int
    rejected: int
    results: list[ValidationResult]


@app.post("/validate/vitals", response_model=BatchValidationResponse)
def validate_vitals_batch(payload: BatchValidationRequest):
    raw_records = payload.records
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

        # 3 & 4. Plausibility + cross-field consistency
        reasons = check_plausible_ranges(record) + check_cross_field_consistency(record)
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

    report_flags_to_admin(payload.hospital_id, results)

    return BatchValidationResponse(
        total=len(results), passed=passed, flagged=flagged, rejected=rejected, results=results
    )


@app.get("/health")
def health():
    return {"status": "ok"}

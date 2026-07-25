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
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, ValidationError

from anomaly import flag_outliers
from rules import check_forbidden_fields, check_plausible_ranges, check_cross_field_consistency
from schema import VitalsRecord

app = FastAPI(title="FedHeal Data Validation Service", version="0.1.0")


class ValidationResult(BaseModel):
    patient_ref: str | None
    status: Literal["passed", "flagged", "rejected"]
    reasons: list[str]


class BatchValidationRequest(BaseModel):
    records: list[dict]


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

    return BatchValidationResponse(
        total=len(results), passed=passed, flagged=flagged, rejected=rejected, results=results
    )


@app.get("/health")
def health():
    return {"status": "ok"}

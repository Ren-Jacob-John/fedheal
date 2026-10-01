"""
Module 8 — Synthesis HTTP service

Run: uvicorn main:app --reload --port 8006
Docs: http://localhost:8006/docs

Data flow (docs/DATA_CONTRACT.md has the field-by-field contract):

    Dashboard  --(user session)-->  POST /synthesize/record {record_id}
        Module 8 reads the stored, validated record from Module 1
            (GET /vitals/{id}, forwarding the USER's own token — tenant
             checks happen in Module 1; this service holds no credential
             for record access)
        -> feature_mapper.map_record(): Module 1 fields -> model inputs
           (explicit table; missing values are reported, never invented)
        -> Module 6 ConditionRouter.route(): specialist selection, required-
           input validation, prediction, SHAP
        -> Module 5 specialist (status card: stub / fallback / training status)
        -> build_synthesis() -> structured response for the dashboard.

Honest about what is real:
  - Routing, prediction, SHAP and synthesis are real code paths.
  - The vitals model is NOT a hospital-trained or federated model. Module 3
    does not export a global model yet, so this service uses an isolated,
    explicitly-labelled demo fallback (model_provider.py) — or, if that is
    disabled, answers 503. Every response says which (`model.*`, `warnings`).
"""
import logging
import os
import sys
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

sys.path.insert(0, str(Path(__file__).parent.parent / "module6-condition-router"))
sys.path.insert(0, str(Path(__file__).parent.parent / "module5-modelzoo"))

from condition_router import (  # noqa: E402
    ConditionRouter, IncompleteDataError, SpecialistUnavailableError, UnknownConditionError,
)
from conditions import CONDITION_REGISTRY, resolve_condition  # noqa: E402
from fusion import FusionLayer  # noqa: E402

import config  # noqa: E402
import feature_mapper  # noqa: E402
import model_provider  # noqa: E402
from audit import audit_event  # noqa: E402
from auth import get_raw_token, require_authenticated_user  # noqa: E402
from docs_theme import mount_custom_docs  # noqa: E402
from synthesis import build_synthesis  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv()  # picks up .env in this folder if present, same as every other module

logger = logging.getLogger("fedheal.synthesis")

AUTH_API_URL = os.environ.get("FEDHEAL_AUTH_API_URL", "http://localhost:8001")

app = FastAPI(title="FedHeal Synthesis Service", version="0.2.0", docs_url=None)
mount_custom_docs(app, accent="#2dd9c4", accent_soft="#d8fbf5")  # teal — Module 8

# Explicit origins only (required + https in staging/production) and only
# what the dashboard uses against this service.
app.add_middleware(
    CORSMiddleware,
    **config.cors_settings(methods=("GET", "POST"), headers=("Authorization", "Content-Type")),
)

router = ConditionRouter()

# Conditions whose specialists take ONLY the vitals modality — i.e. can be
# driven from a Module 1 vitals record. Anything else needs inputs (images,
# genomics, CBC panels) that Module 1's vitals records do not contain.
RECORD_SPECIALISTS = frozenset({"vitals"})

# Fit (or deliberately not) once at startup, and keep the honest description.
VITALS_MODEL_INFO = model_provider.fit_vitals_specialist(router.specialists["vitals"])
if VITALS_MODEL_INFO.source == "none":
    logger.warning("Vitals specialist is UNAVAILABLE: %s", VITALS_MODEL_INFO.detail)


class SynthesizeRecordRequest(BaseModel):
    record_id: str = Field(min_length=1, max_length=64)
    condition: str = Field(default="heart_disease", min_length=1, max_length=64)
    fuse: bool = False


def _error(status_code: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"status": code, "message": message, **extra})


@app.get("/health")
def health():
    return {"status": "ok", "service": "module8-synthesis"}


@app.get("/models/status")
def models_status(condition: str = "heart_disease", _user: dict = Depends(require_authenticated_user)):
    """What would run for a condition, and how real each piece is."""
    try:
        cards = router.status_for_condition(condition)
    except UnknownConditionError as e:
        raise _error(404, "unknown_condition", str(e))
    spec = resolve_condition(condition)
    return {
        "condition": spec.canonical_name,
        "specialists": cards,
        "record_flow_supported": set(spec.specialist_ids) <= RECORD_SPECIALISTS,
        "vitals_model": VITALS_MODEL_INFO.to_dict(),
    }


async def fetch_record(record_id: str, token: str | None) -> dict:
    """Read one stored record from Module 1 as the calling user."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AUTH_API_URL}/vitals/{record_id}", headers=headers)
    except httpx.HTTPError:
        raise _error(502, "upstream_unreachable", "Could not reach Module 1 (auth/vitals service).")
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code in (401, 403, 404):
        detail = "Record not found" if resp.status_code == 404 else "Not permitted for this record"
        raise _error(resp.status_code, {401: "unauthenticated", 403: "forbidden", 404: "record_not_found"}[resp.status_code], detail)
    raise _error(502, "upstream_error", f"Module 1 answered {resp.status_code}.")


def _warnings(status_card: dict, prediction) -> list[dict]:
    out = []
    if status_card.get("is_stub"):
        out.append({"code": "stub_model", "message": "This result comes from a placeholder stub, not a trained model."})
    if status_card.get("is_fallback"):
        out.append({"code": "fallback_model", "message": "This is a fallback model, not the preferred production specialist."})
    if status_card.get("training_status") == "demo_fit":
        out.append({
            "code": "demo_training_data",
            "message": "Model was fitted on public UCI Cleveland demo data (3 real features). "
                       "It is not hospital-trained and not federated.",
        })
    return out


def _explanation(finding, mapped: feature_mapper.MappedInput, unresolved: list[str]) -> dict:
    """The dashboard's explanation block. 'available' only when real SHAP
    contributions exist AND their names are exactly the model's inputs."""
    shap_exp = next((e for e in finding.explanations if e.method == "shap" and not e.is_stub), None)
    expected = [i["feature"] for i in mapped.inputs]
    if shap_exp is None or not isinstance(shap_exp.details, dict):
        reasons = [u for u in unresolved if ":shap:" in u] or ["SHAP explanation was not produced."]
        return {"status": "unavailable", "method": "shap", "reason": "; ".join(reasons),
                "feature_names": expected, "contributions": []}
    if list(shap_exp.details) != expected:
        # Never present attributions whose names don't match the inputs.
        return {"status": "unavailable", "method": "shap",
                "reason": "SHAP feature names did not match the model inputs; withheld.",
                "feature_names": expected, "contributions": []}
    by_feature = {i["feature"]: i["value"] for i in mapped.inputs}
    return {
        "status": "available",
        "method": "shap",
        "reason": None,
        "explained_output": shap_exp.metadata.get("explained_output"),
        "feature_names": expected,
        "contributions": [
            {"feature": name, "value": by_feature[name], "contribution": shap_exp.details[name]}
            for name in expected
        ],
    }


@app.post("/synthesize/record")
async def synthesize_record(
    payload: SynthesizeRecordRequest,
    request: Request,
    user: dict = Depends(require_authenticated_user),
    token: str | None = Depends(get_raw_token),
):
    # Unknown condition -> explicit error, before touching Module 1.
    spec = resolve_condition(payload.condition)
    if spec is None:
        raise _error(404, "unknown_condition", router._unknown_message(payload.condition),
                     known_conditions=sorted({s.canonical_name for s in CONDITION_REGISTRY.values()}))

    if not set(spec.specialist_ids) <= RECORD_SPECIALISTS:
        raise _error(
            422, "unsupported_input",
            f"Condition {spec.canonical_name!r} needs inputs that a Module 1 vitals record does not contain "
            f"(specialists: {spec.specialist_ids}).",
            condition=spec.canonical_name,
            specialists=router.status_for_condition(spec.canonical_name),
        )

    record = await fetch_record(payload.record_id, token)

    # Only validated records: 'flagged' records are awaiting review.
    if record.get("validation_status") != "passed":
        audit_event("synthesis.run", "denied", request=request, actor_user_id=user.get("sub"),
                    actor_role=user.get("role"), hospital_id=user.get("hospital_id"),
                    record_id=payload.record_id, reason="record_not_validated")
        raise _error(409, "record_not_validated",
                     "Only records that passed validation can be synthesized "
                     f"(this record is {record.get('validation_status')!r}).")

    mapped = feature_mapper.map_record(record)
    if mapped.invalid:
        raise _error(422, "invalid_feature_values", "Some stored values are not valid numbers.",
                     invalid_features=mapped.invalid)
    if mapped.missing:
        audit_event("synthesis.run", "denied", request=request, actor_user_id=user.get("sub"),
                    actor_role=user.get("role"), hospital_id=user.get("hospital_id"),
                    record_id=payload.record_id, reason="incomplete_data")
        raise _error(422, "incomplete_data",
                     "This record is missing inputs the model needs; nothing was estimated or filled in.",
                     missing_features=mapped.missing, specialist_id="vitals",
                     record={"record_id": record["id"], "patient_ref": record.get("patient_ref")})

    def run():
        report = router.route(spec.canonical_name, {"vitals": {"features": mapped.features}})
        fused = None
        if payload.fuse and report.findings:
            fused = FusionLayer().combine([f.prediction for f in report.findings])
        return report, build_synthesis(report, spec.specialist_ids, fused=fused)

    try:
        report, synthesis = await run_in_threadpool(run)
    except IncompleteDataError as e:  # defence in depth; the mapper already checked
        raise _error(422, "incomplete_data", str(e), missing_features=e.missing_features, specialist_id=e.specialist_id)
    except SpecialistUnavailableError as e:
        audit_event("synthesis.run", "denied", request=request, actor_user_id=user.get("sub"),
                    actor_role=user.get("role"), hospital_id=user.get("hospital_id"),
                    record_id=payload.record_id, reason="specialist_unavailable")
        raise _error(503, "specialist_unavailable",
                     "The vitals specialist has no model loaded, and no fallback is enabled.",
                     specialist=e.status, model=VITALS_MODEL_INFO.to_dict())
    except UnknownConditionError as e:
        raise _error(404, "unknown_condition", str(e))

    finding = report.findings[0]
    card = finding.status
    pred = finding.prediction
    audit_event("synthesis.run", "success", request=request, actor_user_id=user.get("sub"),
                actor_role=user.get("role"), hospital_id=user.get("hospital_id"), record_id=payload.record_id)

    return {
        "status": "ok",
        "condition": spec.canonical_name,
        "record": {
            "record_id": record["id"],
            "patient_ref": record.get("patient_ref"),
            "validation_status": record.get("validation_status"),
        },
        "inputs": mapped.inputs,
        "specialist": {"specialist_id": finding.specialist_id, **card},
        "model": VITALS_MODEL_INFO.to_dict(),
        "prediction": {
            "label": pred.label,
            "confidence": pred.confidence,
            "is_stub": card.get("is_stub", False),
            "is_fallback": card.get("is_fallback", False),
        },
        "explanation": _explanation(finding, mapped, report.unresolved_explainers),
        "warnings": _warnings(card, pred),
        "synthesis": synthesis.to_dict(),
    }


@app.post("/synthesize/heart_disease", status_code=410)
def synthesize_heart_disease_removed(request: Request, _user: dict = Depends(require_authenticated_user)):
    """Retired: hand-entered features. The old body was 8 numbers in a legacy
    feature space (age, resting_bp, cholesterol, ...) that matched no stored
    data. Use POST /synthesize/record with a validated record's id."""
    raise _error(410, "endpoint_removed",
                 "Manual feature entry was removed. POST /synthesize/record with {\"record_id\": ...}.")

"""
Module 7 — Admin / Platform Module (the operator's view)

Run: uvicorn main:app --reload --port 8005
Docs: http://localhost:8005/docs

This is the last of the 8 modules from the original proposal
("Admin/Platform Module (you, the operator)") and the first module whose
whole job is cross-cutting: it has almost no data of its own, it exists to
give the platform operator one place to see what Module 1 (hospitals),
Module 2 (validation flags), and Module 3 (federated rounds) are each
doing, without duplicating any of their data.

What's real vs. a prototype simplification, be upfront about both:
  - Hospital list/activate-deactivate: REAL — proxies live to Module 1,
    which is the actual source of truth (see hospitals_client.py). This
    also required adding one new endpoint to Module 1 itself:
    `PATCH /hospitals/{id}` (super_admin only) — see module1-auth/main.py.
  - Training-round history: REAL, but requires Module 3 to report in.
    module3-fedlearning/simulate.py now does this automatically after
    each round (best-effort — if this service isn't running, the
    simulation still runs standalone, it just has nothing to report to).
  - Validation-flag summaries: REAL, same pattern — module2-validation
    now posts a rolled-up summary here after each batch validation call.
  - Retraining eligibility is count-only and off unless configured.
    Hospital runners poll durable, hospital-scoped requests; model
    candidates still require the existing validation and manual promotion.
"""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

import config
import hospitals_client
import models
import schemas
from audit import audit_event
import service_auth
from auth import (
    get_raw_token, require_flag_report, require_retraining_runner,
    require_round_report, require_super_admin,
)
from database import get_db
from repo import Repo
from docs_theme import mount_custom_docs
import model_registry
import service_auth

# Storage is Firestore (see database.py / docstore.py / repo.py): no schema to create or migrate.
# Composite indexes for the ordered queries are declared in firestore.indexes.json.

app = FastAPI(title="FedHeal Admin/Platform Service", version="0.1.0", docs_url=None)
mount_custom_docs(app, accent="#7c3fc9", accent_soft="#efe3fc")  # purple — Module 7

# Explicit origins only (FEDHEAL_DASHBOARD_ORIGIN; required + https in
# staging/production) and only the methods/headers the dashboard uses here.
app.add_middleware(
    CORSMiddleware,
    **config.cors_settings(methods=("GET", "POST", "PATCH"), headers=("Authorization", "Content-Type")),
)

app.include_router(model_registry.build_router())

@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Hospital oversight (proxies Module 1, adds nothing of its own) ----------

@app.get("/admin/hospitals")
async def list_hospitals(token: str | None = Depends(get_raw_token), _=Depends(require_super_admin)):
    try:
        return await hospitals_client.list_hospitals(token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Module 1 (auth service): {e}")


@app.patch("/admin/hospitals/{hospital_id}")
async def set_hospital_status(
    hospital_id: str,
    payload: schemas.HospitalStatusUpdate,
    request: Request,
    token: str | None = Depends(get_raw_token),
    admin: dict = Depends(require_super_admin),
):
    try:
        result = await hospitals_client.set_hospital_status(hospital_id, payload.is_active, token)
    except Exception as e:
        audit_event("hospital.update", "failure", request=request, actor_user_id=admin.get("sub"),
                    actor_role=admin.get("role"), target_hospital_id=hospital_id, reason="upstream_error")
        raise HTTPException(status_code=502, detail=f"Could not reach Module 1 (auth service): {e}")
    audit_event("hospital.update", "success", request=request, actor_user_id=admin.get("sub"),
                actor_role=admin.get("role"), target_hospital_id=hospital_id, is_active=payload.is_active)
    return result


# ---------- Training-round history ----------
# POST is service-to-service (Module 3 -> here), guarded by the shared
# service key, NOT the human JWT — Module 3 isn't a logged-in user.

@app.post("/admin/rounds", response_model=schemas.TrainingRoundOut)
def report_round(
    payload: schemas.TrainingRoundIn,
    db: Repo = Depends(get_db),
    _=Depends(require_round_report),
):
    return db.add_round(models.TrainingRound(**payload.model_dump()))


@app.get("/admin/rounds", response_model=list[schemas.TrainingRoundOut])
def list_rounds(
    limit: int = 20,
    db: Repo = Depends(get_db),
    _=Depends(require_super_admin),
):
    return db.list_rounds(limit)


@app.post("/admin/rounds/trigger")
def trigger_round(
    request: Request,
    hospital_id: str | None = Query(default=None, min_length=1),
    db: Repo = Depends(get_db),
    admin: dict = Depends(require_super_admin),
):
    """
    Return the already-gated per-hospital round request. This route no longer
    launches a local simulator; only eligible-record reports create requests.
    """
    if hospital_id is None:
        raise HTTPException(status_code=422, detail="hospital_id is required")
    requests = db.list_retraining(hospital_id, limit=100)
    pending = next((row for row in requests if row.status in {"PENDING", "CLAIMED"}), None)
    if pending is None:
        raise HTTPException(status_code=409, detail="No eligible retraining request is pending for this hospital")
    audit_event("rounds.trigger", "success", request=request, actor_user_id=admin.get("sub"),
                actor_role=admin.get("role"), target_hospital_id=hospital_id,
                request_id=pending.id)
    return pending


@app.post("/admin/retraining/eligibility")
def report_retraining_eligibility(
    payload: schemas.RetrainingEligibilityIn,
    request: Request,
    claims: dict = Depends(require_retraining_runner),
    db: Repo = Depends(get_db),
):
    """Accept only a scoped count; patient rows, labels and identifiers are never sent."""
    hospital_id = service_auth.hospital_scope(claims)
    if hospital_id is None:
        raise HTTPException(status_code=403, detail="Runner credential must be hospital-scoped")
    threshold = config.env_int("FEDHEAL_RETRAIN_MIN_ELIGIBLE_RECORDS", 0, minimum=0)
    if threshold == 0 or payload.eligible_records < threshold:
        return {"status": "disabled" if threshold == 0 else "below_threshold", "request_id": None}
    status, request_id = db.consider_retraining(hospital_id, payload.eligible_records, threshold)
    audit_event("retraining.eligibility", "success", request=request, actor_service="module3",
                target_hospital_id=hospital_id, eligible_records=payload.eligible_records,
                request_id=request_id)
    return {"status": status, "request_id": request_id}


@app.get("/admin/retraining/requests/next", response_model=schemas.RetrainingRequestOut | None)
def claim_retraining_request(
    request: Request,
    claims: dict = Depends(require_retraining_runner),
    db: Repo = Depends(get_db),
):
    hospital_id = service_auth.hospital_scope(claims)
    if hospital_id is None:
        raise HTTPException(status_code=403, detail="Runner credential must be hospital-scoped")
    claimed = db.claim_retraining(hospital_id)
    if claimed is not None:
        audit_event("retraining.claim", "success", request=request, actor_service="module3",
                    target_hospital_id=hospital_id, request_id=claimed.id)
    return claimed


@app.post("/admin/retraining/requests/complete", response_model=schemas.RetrainingRequestOut)
def complete_retraining_request(
    payload: schemas.RetrainingCompletionIn,
    request: Request,
    claims: dict = Depends(require_retraining_runner),
    db: Repo = Depends(get_db),
):
    hospital_id = service_auth.hospital_scope(claims)
    if hospital_id is None:
        raise HTTPException(status_code=403, detail="Runner credential must be hospital-scoped")
    if payload.status not in {"COMPLETED", "FAILED"}:
        raise HTTPException(status_code=422, detail="status must be COMPLETED or FAILED")
    if payload.status == "COMPLETED":
        existing = db.get_retraining(payload.request_id)
        if existing is None or existing.hospital_id != hospital_id or existing.status != "CLAIMED":
            raise HTTPException(status_code=404, detail="Request not found or not claimable by this hospital")
        if not existing.candidate_id:
            raise HTTPException(status_code=409, detail="A registered candidate is required before completion")
    completed = db.complete_retraining(
        payload.request_id, hospital_id, payload.status, payload.eligible_records,
    )
    if completed is None:
        raise HTTPException(status_code=404, detail="Request not found or not claimable by this hospital")
    audit_event("retraining.complete", "success", request=request, actor_service="module3",
                target_hospital_id=hospital_id, request_id=completed.id, status=completed.status)
    return completed


@app.get("/admin/retraining/requests/{request_id}/candidate",
         response_model=schemas.RetrainingCandidateStatusOut)
def retraining_candidate_status(
    request_id: str,
    request: Request,
    claims: dict = Depends(require_retraining_runner),
    db: Repo = Depends(get_db),
):
    hospital_id = service_auth.hospital_scope(claims)
    if hospital_id is None:
        raise HTTPException(status_code=403, detail="Runner credential must be hospital-scoped")
    retraining_request = db.get_retraining(request_id)
    if retraining_request is None or retraining_request.hospital_id != hospital_id:
        raise HTTPException(status_code=404, detail="Request not found for this hospital")
    if not retraining_request.candidate_id:
        return schemas.RetrainingCandidateStatusOut(registered=False)
    candidate = db.get_model(retraining_request.candidate_id)
    if candidate is None:
        raise HTTPException(status_code=409, detail="Candidate linkage exists but the registry entry is missing")
    if request_id not in candidate.training_metadata.get("retraining_request_ids", []):
        raise HTTPException(status_code=409, detail="Candidate linkage does not match its provenance")
    return schemas.RetrainingCandidateStatusOut(
        registered=True,
        candidate_id=candidate.id,
        version=candidate.version,
        deployment_status=candidate.deployment_status,
    )


@app.get("/admin/retraining/requests", response_model=list[schemas.RetrainingRequestOut])
def list_retraining_requests(
    hospital_id: str | None = None,
    limit: int = 100,
    db: Repo = Depends(get_db),
    _=Depends(require_super_admin),
):
    return db.list_retraining(hospital_id, min(max(limit, 1), 500))


# ---------- Validation-flag summaries ----------

@app.post("/admin/flags", response_model=schemas.ValidationFlagOut)
def report_flag(
    payload: schemas.ValidationFlagIn,
    db: Repo = Depends(get_db),
    claims=Depends(require_flag_report),
    request: Request = None,
):
    # The credential names ONE hospital; a flag about any other hospital is refused (no unscoped cross-tenant reporting).
    if service_auth.hospital_scope(claims) != payload.hospital_id:
        audit_event("service_authz.failure", "denied", request=request, actor_service="module2",
                    reason="hospital_scope_mismatch", resource_type="flag")
        raise HTTPException(status_code=403, detail="Credential is not authorized for this hospital")
    return db.add_flag(models.ValidationFlag(**payload.model_dump()))


@app.get("/admin/flags", response_model=list[schemas.ValidationFlagOut])
def list_flags(
    hospital_id: str | None = None,
    limit: int = 50,
    db: Repo = Depends(get_db),
    _=Depends(require_super_admin),
):
    return db.list_flags(hospital_id, limit)


# ---------- One-shot overview, what an admin dashboard home screen wants ----------

@app.get("/admin/overview", response_model=schemas.OverviewOut)
async def overview(
    token: str | None = Depends(get_raw_token),
    db: Repo = Depends(get_db),
    _=Depends(require_super_admin),
):
    try:
        hospitals = await hospitals_client.list_hospitals(token)
    except Exception:
        hospitals = []  # Module 1 unreachable — degrade gracefully rather than 502 the whole overview

    active = sum(1 for h in hospitals if h.get("is_active"))

    latest = db.list_rounds(1)
    latest_round = latest[0] if latest else None
    total_rounds = db.count_rounds()
    total_flags = db.count_flags()

    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_flags = db.count_flags(since=seven_days_ago)

    return schemas.OverviewOut(
        total_hospitals=len(hospitals),
        active_hospitals=active,
        inactive_hospitals=len(hospitals) - active,
        latest_round_number=latest_round.round_number if latest_round else None,
        latest_global_accuracy=latest_round.global_accuracy if latest_round else None,
        total_rounds_recorded=total_rounds,
        total_flags=total_flags,
        flags_last_7_days=recent_flags,
    )

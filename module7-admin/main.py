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
  - "Trigger a new federated round": a REAL, working button, but it
    triggers the CURRENT single-process simulate.py as a subprocess,
    not real separate hospital machines. That's the honest state of
    Module 3 too at this stage (see its README) — when Module 3
    graduates to real networked hospitals (its server.py + a client
    runner), this endpoint's job stays the same: kick off training and
    let the round-completion get reported back here.
"""
import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

import hospitals_client
import models
import schemas
from auth import oauth2_scheme, require_service_key, require_super_admin
from database import Base, engine, get_db

Base.metadata.create_all(bind=engine)

app = FastAPI(title="FedHeal Admin/Platform Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Path to Module 3's simulate.py, relative to this file, so /rounds/trigger
# works regardless of which directory uvicorn was launched from.
MODULE3_DIR = Path(__file__).resolve().parent.parent / "module3-fedlearning"


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- Hospital oversight (proxies Module 1, adds nothing of its own) ----------

@app.get("/admin/hospitals")
async def list_hospitals(token: str = Depends(oauth2_scheme), _=Depends(require_super_admin)):
    try:
        return await hospitals_client.list_hospitals(token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Module 1 (auth service): {e}")


@app.patch("/admin/hospitals/{hospital_id}")
async def set_hospital_status(
    hospital_id: str,
    payload: schemas.HospitalStatusUpdate,
    token: str = Depends(oauth2_scheme),
    _=Depends(require_super_admin),
):
    try:
        return await hospitals_client.set_hospital_status(hospital_id, payload.is_active, token)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Module 1 (auth service): {e}")


# ---------- Training-round history ----------
# POST is service-to-service (Module 3 -> here), guarded by the shared
# service key, NOT the human JWT — Module 3 isn't a logged-in user.

@app.post("/admin/rounds", response_model=schemas.TrainingRoundOut)
def report_round(
    payload: schemas.TrainingRoundIn,
    db: Session = Depends(get_db),
    _=Depends(require_service_key),
):
    record = models.TrainingRound(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.get("/admin/rounds", response_model=list[schemas.TrainingRoundOut])
def list_rounds(
    limit: int = 20,
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
):
    return (
        db.query(models.TrainingRound)
        .order_by(models.TrainingRound.round_number.desc())
        .limit(limit)
        .all()
    )


@app.post("/admin/rounds/trigger")
def trigger_round(_=Depends(require_super_admin)):
    """
    Kicks off Module 3's simulate.py as a background subprocess and
    returns immediately. The prototype-honest version of "trigger a new
    federated training round" — see module docstring above for what this
    graduates to.
    """
    if not (MODULE3_DIR / "simulate.py").exists():
        raise HTTPException(status_code=500, detail=f"simulate.py not found at {MODULE3_DIR}")

    subprocess.Popen(
        [sys.executable, "simulate.py"],
        cwd=str(MODULE3_DIR),
        env={**os.environ, "FEDHEAL_ADMIN_API_URL": os.environ.get(
            "FEDHEAL_ADMIN_API_URL", "http://localhost:8005"
        )},
    )
    return {
        "status": "triggered",
        "note": "Running module3-fedlearning/simulate.py in the background. "
                "Poll GET /admin/rounds — each round reports itself as it completes.",
    }


# ---------- Validation-flag summaries ----------

@app.post("/admin/flags", response_model=schemas.ValidationFlagOut)
def report_flag(
    payload: schemas.ValidationFlagIn,
    db: Session = Depends(get_db),
    _=Depends(require_service_key),
):
    record = models.ValidationFlag(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.get("/admin/flags", response_model=list[schemas.ValidationFlagOut])
def list_flags(
    hospital_id: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
):
    query = db.query(models.ValidationFlag)
    if hospital_id:
        query = query.filter(models.ValidationFlag.hospital_id == hospital_id)
    return query.order_by(models.ValidationFlag.reported_at.desc()).limit(limit).all()


# ---------- One-shot overview, what an admin dashboard home screen wants ----------

@app.get("/admin/overview", response_model=schemas.OverviewOut)
async def overview(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    _=Depends(require_super_admin),
):
    try:
        hospitals = await hospitals_client.list_hospitals(token)
    except Exception:
        hospitals = []  # Module 1 unreachable — degrade gracefully rather than 502 the whole overview

    active = sum(1 for h in hospitals if h.get("is_active"))

    latest_round = (
        db.query(models.TrainingRound)
        .order_by(models.TrainingRound.round_number.desc())
        .first()
    )
    total_rounds = db.query(func.count(models.TrainingRound.id)).scalar() or 0
    total_flags = db.query(func.count(models.ValidationFlag.id)).scalar() or 0

    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_flags = (
        db.query(func.count(models.ValidationFlag.id))
        .filter(models.ValidationFlag.reported_at >= seven_days_ago)
        .scalar()
        or 0
    )

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

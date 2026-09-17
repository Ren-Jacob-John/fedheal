"""
Module 8 — Synthesis HTTP service (new in Sprint B)

Run: uvicorn main:app --reload --port 8006
Docs: http://localhost:8006/docs

`synthesis.py` (and everything it imports from Modules 5/6) stays a plain
library — this file is a thin FastAPI shell around it, so Module 4's new
Synthesis view has an HTTP endpoint to call instead of embedding Python
imports across service boundaries. See module8-synthesis.md's "HTTP
surface" section for the full rationale, including why this is
deliberately scoped to one condition for now.

Honest about what's real vs. a prototype simplification, same as every
other module's docstring:
  - The condition routing, specialist prediction, SHAP explanation, and
    synthesis aggregation are all REAL — this calls the exact same
    `ConditionRouter.route()` -> `build_synthesis()` path `demo.py` does.
  - The vitals specialist's "training" is NOT real per-hospital data —
    nothing in this project has a persisted, hospital-trained vitals
    model yet (see module3-fedlearning's own status notes). At startup,
    this service fits the specialist on the same synthetic distribution
    demo.py uses, purely so `/synthesize/heart_disease` has something to
    predict with. Swapping in a real fitted model — e.g. the global model
    module3-fedlearning's FedAvg produces — is a follow-on, tracked in
    module8-synthesis.md, not something this endpoint pretends to do
    today.
"""
import sys
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).parent.parent / "module6-condition-router"))
sys.path.insert(0, str(Path(__file__).parent.parent / "module5-modelzoo"))

from condition_router import ConditionRouter, UnknownConditionError  # noqa: E402
from conditions import resolve_condition  # noqa: E402
from fusion import FusionLayer  # noqa: E402

from auth import require_authenticated_user  # noqa: E402
from docs_theme import mount_custom_docs  # noqa: E402
from synthesis import build_synthesis  # noqa: E402

import os  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv()  # picks up .env in this folder if present, same as every other module

app = FastAPI(title="FedHeal Synthesis Service", version="0.1.0", docs_url=None)
mount_custom_docs(app, accent="#2dd9c4", accent_soft="#d8fbf5")  # teal — Module 8

_dashboard_origins = os.environ.get("FEDHEAL_DASHBOARD_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _dashboard_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = ConditionRouter()

# Same synthetic-fit pattern module8-synthesis/demo.py and
# module6-condition-router/demo.py already use for this exact specialist
# — see this file's module docstring for why. Fitting once at import time
# (rather than per-request) keeps /synthesize/heart_disease fast; the
# specialist itself is stateless-at-inference after fit(), same as every
# other call site in this project.
_rng = np.random.default_rng(7)
_fit_X = _rng.normal(size=(200, 8))
_fit_y = (_fit_X[:, 0] + _fit_X[:, 4] - _fit_X[:, 3] > 0).astype(int)
router.specialists["vitals"].fit(_fit_X, _fit_y)


class HeartDiseaseCase(BaseModel):
    # tabular_vitals.FEATURE_NAMES order: age, resting_bp, cholesterol,
    # max_heart_rate, bmi, glucose, num_medications, prior_admissions.
    # Module 1's stored vitals-upload schema doesn't map onto this 1:1 yet
    # (see docs/DEVELOPMENT_PLAN.md's Sprint A risk register on the vitals
    # schema) — until that's reconciled, the case is entered directly in
    # the model's own feature space, same as demo.py's synthetic cases.
    features: list[float] = Field(min_length=8, max_length=8)
    fuse: bool = False


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/synthesize/heart_disease")
def synthesize_heart_disease(
    payload: HeartDiseaseCase,
    _user: dict = Depends(require_authenticated_user),
):
    spec = resolve_condition("heart_disease")
    case_data = {"vitals": {"features": payload.features}}

    try:
        report = router.route("heart_disease", case_data)
    except UnknownConditionError as e:
        # Shouldn't happen for a hardcoded condition name, but never mask
        # this behind a 500 if conditions.py ever changes underneath us.
        raise HTTPException(status_code=500, detail=str(e))

    fused = None
    if payload.fuse and report.findings:
        fused = FusionLayer().combine([f.prediction for f in report.findings])

    synthesis = build_synthesis(report, spec.specialist_ids, fused=fused)
    return synthesis.to_dict()

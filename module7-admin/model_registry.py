"""
Model registry routes + the validation gate (P0).

The gate is a pure function (`evaluate_candidate`) so it is unit-testable
without HTTP or a database. Thresholds are DEMO/engineering thresholds taken
from environment variables; they are not clinical acceptance criteria and
must not be described as such.
"""
import math
import os
import re
import struct
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import models
from audit import audit_event
from auth import require_model_candidate_credential, require_promoted_model_read, require_super_admin
from database import get_db

HEX64 = re.compile(r"^[0-9a-f]{64}$")

# Keys that must never appear in anything the federation side registers.
FORBIDDEN_KEYS = frozenset({
    "patient_ref", "patient_id", "patient_name", "name", "records", "rows", "csv", "vitals", "history",
    "medical_history", "notes", "note", "image", "images", "scan", "scans", "features", "x", "y", "labels",
    "dataset", "email", "payload", "raw",
})
MAX_STR = 256
MAX_LIST = 200


def assert_no_raw_data(value, path: str = "$") -> None:
    """Registry payloads may hold only ids, hashes, short strings, numbers,
    booleans and small aggregates. Anything that looks like data is refused."""
    if isinstance(value, dict):
        for k, v in value.items():
            if str(k).lower() in FORBIDDEN_KEYS:
                raise HTTPException(status_code=422, detail=f"Field {path}.{k} is not allowed in the registry: "
                                                            "raw/patient-level data must never reach the federation side")
            assert_no_raw_data(v, f"{path}.{k}")
    elif isinstance(value, list):
        if len(value) > MAX_LIST:
            raise HTTPException(status_code=422, detail=f"{path} has too many items for registry metadata")
        for i, v in enumerate(value):
            assert_no_raw_data(v, f"{path}[{i}]")
    elif isinstance(value, str):
        if len(value) > MAX_STR:
            raise HTTPException(status_code=422, detail=f"{path} is too long for registry metadata")


def canonical_hash(coef: list, intercept: list) -> str:
    """Same canonical form as module3-fedlearning/federation_registry.artifact_hash (dtype <f8, shape, bytes),
    in pure Python so the registry can re-derive the hash itself instead of trusting the caller's."""
    import hashlib
    h = hashlib.sha256()
    h.update(str((len(coef), len(coef[0]))).encode())
    h.update(struct.pack(f"<{len(coef[0])}d", *coef[0]))
    h.update(str((len(intercept),)).encode())
    h.update(struct.pack(f"<{len(intercept)}d", *intercept))
    return h.hexdigest()


def validate_parameters(parameters: dict, input_spec: dict) -> int:
    """Shape/finite checks for a small linear model; returns the feature count."""
    try:
        coef, intercept = parameters["coef"], parameters["intercept"]
        n = len(coef[0])
        ok = (len(coef) == 1 and 1 <= n <= 64 and len(intercept) == 1
              and all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                      for v in [*coef[0], *intercept]))
        spec_ok = (isinstance(input_spec, dict) and len(input_spec.get("feature_names", [])) == n
                   and all(isinstance(x, str) and 0 < len(x) <= 64 for x in input_spec["feature_names"])
                   and len(input_spec.get("center", [])) == n and len(input_spec.get("scale", [])) == n
                   and all(isinstance(v, (int, float)) and math.isfinite(v) for v in input_spec["center"])
                   and all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in input_spec["scale"]))
    except (KeyError, TypeError, IndexError):
        ok = spec_ok = False
    if not (ok and spec_ok):
        raise HTTPException(status_code=422, detail="parameters/input_spec must describe one linear model "
                                                    "(1 x n coefficients, 1 intercept, matching feature_names/center/scale)")
    return n


class Policy:
    def __init__(self):
        f = lambda k, d: float(os.environ.get(k, d))  # noqa: E731
        self.min_accuracy = f("FEDHEAL_GATE_MIN_ACCURACY", 0.60)
        self.min_eval_examples = int(os.environ.get("FEDHEAL_GATE_MIN_EVAL_EXAMPLES", 50))
        self.max_regression = f("FEDHEAL_GATE_MAX_REGRESSION", 0.02)
        self.min_hospitals = int(os.environ.get("FEDHEAL_GATE_MIN_HOSPITALS", 2))
        self.max_hospital_gap = f("FEDHEAL_GATE_MAX_HOSPITAL_GAP", 0.25)
        self.min_margin_over_majority = f("FEDHEAL_GATE_MIN_MARGIN_OVER_MAJORITY", 0.05)


def _num(v) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def evaluate_candidate(candidate: dict, current: Optional[dict], policy: Policy) -> dict:
    """candidate/current: {metrics, training_metadata, participating_hospitals, artifact_hash}.
    Returns {"passed": bool, "checks": [{name, status: PASS|FAIL|SKIPPED, detail}]}."""
    checks = []

    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})

    m = candidate.get("metrics") or {}
    meta = candidate.get("training_metadata") or {}

    hash_ok = bool(HEX64.match(candidate.get("artifact_hash") or ""))
    verified = candidate.get("parameters_verified") is True
    add("integrity", "PASS" if hash_ok and verified else "FAIL",
        "weights were supplied and the registry re-derived the artifact hash from them" if hash_ok and verified
        else ("artifact_hash missing or malformed" if not hash_ok
              else "no verifiable weights were supplied; there would be nothing to deploy"))

    hospitals = candidate.get("participating_hospitals") or []
    add("participation", "PASS" if len(set(hospitals)) >= policy.min_hospitals else "FAIL",
        f"{len(set(hospitals))} participating hospital(s); policy minimum {policy.min_hospitals}")

    ok = meta.get("validated_records_only") is True and meta.get("labels_from_hospital_only") is True
    add("data_quality", "PASS" if ok else "FAIL",
        "training used only validated records with hospital-sourced labels" if ok
        else "training metadata does not attest validated-only records with hospital-sourced labels")

    acc, n_eval = _num(m.get("accuracy")), _num(m.get("n_eval"))
    if acc is None or n_eval is None:
        add("minimum_metrics", "FAIL", "metrics.accuracy and metrics.n_eval are required")
    elif n_eval < policy.min_eval_examples:
        add("minimum_metrics", "FAIL", f"evaluated on {int(n_eval)} examples; policy minimum {policy.min_eval_examples}")
    elif acc < policy.min_accuracy:
        add("minimum_metrics", "FAIL", f"accuracy {acc:.3f} is below the policy minimum {policy.min_accuracy:.2f}")
    else:
        add("minimum_metrics", "PASS", f"accuracy {acc:.3f} on {int(n_eval)} examples (policy minimum "
                                       f"{policy.min_accuracy:.2f}, {policy.min_eval_examples} examples)")

    floor = _num(m.get("majority_class_floor"))
    if floor is None or acc is None:
        add("beats_majority_baseline", "SKIPPED", "majority_class_floor not provided; baseline comparison not possible")
    elif acc >= floor + policy.min_margin_over_majority:
        add("beats_majority_baseline", "PASS", f"accuracy {acc:.3f} exceeds the always-predict-majority floor "
                                               f"{floor:.3f} by at least {policy.min_margin_over_majority:.2f}")
    else:
        add("beats_majority_baseline", "FAIL", f"accuracy {acc:.3f} is not at least {policy.min_margin_over_majority:.2f} "
                                               f"above the always-predict-majority floor {floor:.3f}; "
                                               "the model has not been shown to beat a trivial predictor")

    if current is None:
        add("regression", "SKIPPED", "no deployed model to compare against")
    else:
        cacc = _num((current.get("metrics") or {}).get("accuracy"))
        if acc is None or cacc is None:
            add("regression", "FAIL", "cannot compare: accuracy missing on candidate or current model")
        elif acc + policy.max_regression < cacc:
            add("regression", "FAIL", f"candidate accuracy {acc:.3f} is worse than the deployed model's "
                                      f"{cacc:.3f} by more than the allowed {policy.max_regression:.2f}")
        else:
            add("regression", "PASS", f"candidate {acc:.3f} vs deployed {cacc:.3f} "
                                      f"(allowed regression {policy.max_regression:.2f})")

    per = m.get("per_hospital_accuracy")
    if not isinstance(per, dict) or len(per) < 2:
        add("fairness", "SKIPPED", "per-hospital accuracy not provided; no cross-site fairness check was possible")
    else:
        vals = [_num(v) for v in per.values()]
        if any(v is None for v in vals):
            add("fairness", "FAIL", "per_hospital_accuracy contains non-numeric values")
        else:
            gap = max(vals) - min(vals)
            add("fairness", "PASS" if gap <= policy.max_hospital_gap else "FAIL",
                f"largest between-hospital accuracy gap {gap:.3f} (policy maximum {policy.max_hospital_gap:.2f}); "
                "this is a cross-site check only, not a demographic fairness assessment")

    return {"passed": all(c["status"] != "FAIL" for c in checks), "checks": checks}


# ---------------- schemas ----------------

class CandidateIn(BaseModel):
    model_name: str = Field(min_length=1, max_length=80)
    condition: str = Field(min_length=1, max_length=64)
    training_round: int = Field(ge=0)
    participating_hospitals: list[str] = Field(default_factory=list)
    training_metadata: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    artifact_hash: str = Field(min_length=1, max_length=128)
    parameters: Optional[dict] = None
    input_spec: Optional[dict] = None


class ModelVersionOut(BaseModel):
    id: str
    model_name: str
    version: str
    parent_version: Optional[str]
    condition: str
    training_round: int
    participating_hospitals: list
    training_metadata: dict
    metrics: dict
    validation_status: str
    validation_report: Optional[dict]
    deployment_status: str
    artifact_hash: str
    created_at: Optional[datetime]
    approved_at: Optional[datetime]
    approved_by: Optional[str]

    class Config:
        from_attributes = True


class PromoteIn(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


def _current(db: Session, model_name: str, condition: str) -> Optional[models.ModelVersion]:
    return (db.query(models.ModelVersion)
            .filter_by(model_name=model_name, condition=condition, deployment_status="DEPLOYED").first())


def build_router() -> APIRouter:
    router = APIRouter()
    policy = Policy()

    @router.post("/admin/models/candidates", response_model=ModelVersionOut, status_code=201)
    def register_candidate(payload: CandidateIn, request: Request, db: Session = Depends(get_db),
                           _=Depends(require_model_candidate_credential)):
        """Module 3 registers the global model a federated round produced.
        Registration deploys nothing."""
        assert_no_raw_data(payload.training_metadata, "$.training_metadata")
        assert_no_raw_data(payload.metrics, "$.metrics")
        assert_no_raw_data(payload.participating_hospitals, "$.participating_hospitals")
        if payload.parameters is not None:
            validate_parameters(payload.parameters, payload.input_spec or {})
            if canonical_hash(payload.parameters["coef"], payload.parameters["intercept"]) != payload.artifact_hash:
                audit_event("model.register", "denied", request=request, actor_service="module3",
                            reason="artifact_hash_mismatch")
                raise HTTPException(status_code=422, detail="artifact_hash does not match the supplied parameters")
        n = db.query(models.ModelVersion).filter_by(model_name=payload.model_name,
                                                    condition=payload.condition).count()
        cur = _current(db, payload.model_name, payload.condition)
        row = models.ModelVersion(
            model_name=payload.model_name, condition=payload.condition, version=f"v{n + 1}",
            parent_version=cur.version if cur else None, training_round=payload.training_round,
            participating_hospitals=payload.participating_hospitals,
            training_metadata=payload.training_metadata, metrics=payload.metrics,
            artifact_hash=payload.artifact_hash, parameters=payload.parameters, input_spec=payload.input_spec,
            validation_status="PENDING", deployment_status="CANDIDATE",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        audit_event("model.register", "success", request=request, actor_service="module3",
                    resource_type="model", resource_id=row.id, model_version=row.version,
                    round_number=row.training_round)
        return row

    @router.get("/admin/models", response_model=list[ModelVersionOut])
    def list_models(condition: Optional[str] = None, db: Session = Depends(get_db),
                    _=Depends(require_super_admin)):
        q = db.query(models.ModelVersion)
        if condition:
            q = q.filter_by(condition=condition)
        return q.order_by(models.ModelVersion.created_at.desc()).limit(200).all()

    def _get(db, model_id):
        row = db.query(models.ModelVersion).filter_by(id=model_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Model version not found")
        return row

    @router.post("/admin/models/{model_id}/validate", response_model=ModelVersionOut)
    def validate_model(model_id: str, request: Request, db: Session = Depends(get_db),
                       admin: dict = Depends(require_super_admin)):
        row = _get(db, model_id)
        if row.deployment_status != "CANDIDATE":
            raise HTTPException(status_code=409, detail=f"Only CANDIDATE models can be validated "
                                                        f"(this one is {row.deployment_status})")
        cur = _current(db, row.model_name, row.condition)
        report = evaluate_candidate(
            {"metrics": row.metrics, "training_metadata": row.training_metadata,
             "participating_hospitals": row.participating_hospitals, "artifact_hash": row.artifact_hash,
             "parameters_verified": row.parameters is not None},
            {"metrics": cur.metrics} if cur else None, policy)
        report["compared_against"] = cur.version if cur else None
        row.validation_report = report
        row.validation_status = "PASSED" if report["passed"] else "FAILED"
        row.deployment_status = "VALIDATED" if report["passed"] else "REJECTED"
        db.commit()
        db.refresh(row)
        audit_event("model.validate", "success" if report["passed"] else "denied", request=request,
                    actor_user_id=admin.get("sub"), actor_role=admin.get("role"),
                    resource_type="model", resource_id=row.id, model_version=row.version)
        return row

    @router.post("/admin/models/{model_id}/promote", response_model=ModelVersionOut)
    def promote_model(model_id: str, payload: PromoteIn, request: Request, db: Session = Depends(get_db),
                      admin: dict = Depends(require_super_admin)):
        """The approval gate: an explicit super_admin action, allowed only for a model that PASSED validation."""
        row = _get(db, model_id)
        if row.deployment_status != "VALIDATED" or row.validation_status != "PASSED":
            audit_event("model.promote", "denied", request=request, actor_user_id=admin.get("sub"),
                        actor_role=admin.get("role"), resource_type="model", resource_id=row.id,
                        reason="not_validated")
            raise HTTPException(status_code=409, detail="Only a model that passed validation can be promoted "
                                                        f"(this one is {row.deployment_status})")
        cur = _current(db, row.model_name, row.condition)
        if cur is not None:
            cur.deployment_status = "RETIRED"
            row.replaces_id = cur.id
            row.parent_version = cur.version
        row.deployment_status = "DEPLOYED"
        row.approved_at = datetime.now(timezone.utc)
        row.approved_by = admin.get("sub")
        db.commit()
        db.refresh(row)
        audit_event("model.promote", "success", request=request, actor_user_id=admin.get("sub"),
                    actor_role=admin.get("role"), resource_type="model", resource_id=row.id,
                    model_version=row.version)
        return row

    @router.post("/admin/models/rollback", response_model=ModelVersionOut)
    def rollback(model_name: str, condition: str, request: Request, db: Session = Depends(get_db),
                 admin: dict = Depends(require_super_admin)):
        cur = _current(db, model_name, condition)
        if cur is None or not cur.replaces_id:
            raise HTTPException(status_code=409, detail="There is no previous approved model to roll back to")
        prev = db.query(models.ModelVersion).filter_by(id=cur.replaces_id).first()
        if prev is None or prev.deployment_status != "RETIRED":
            raise HTTPException(status_code=409, detail="The previous approved model is not available for rollback")
        cur.deployment_status = "ROLLED_BACK"
        prev.deployment_status = "DEPLOYED"
        db.commit()
        db.refresh(prev)
        audit_event("model.rollback", "success", request=request, actor_user_id=admin.get("sub"),
                    actor_role=admin.get("role"), resource_type="model", resource_id=prev.id,
                    model_version=prev.version)
        return prev

    @router.get("/admin/models/promoted")
    def promoted_model(request: Request, condition: str, model_name: Optional[str] = None,
                       db: Session = Depends(get_db), _=Depends(require_promoted_model_read)):
        """What Module 8 serves: the currently DEPLOYED (promoted) model with its weights and provenance.
        Aggregates and weights only; nothing patient-level exists in the registry."""
        q = db.query(models.ModelVersion).filter_by(condition=condition, deployment_status="DEPLOYED")
        if model_name:
            q = q.filter_by(model_name=model_name)
        row = q.order_by(models.ModelVersion.approved_at.desc()).first()
        if row is None or row.parameters is None:
            raise HTTPException(status_code=404, detail="No promoted model for this condition")
        return {"id": row.id, "model_name": row.model_name, "version": row.version,
                "parent_version": row.parent_version, "condition": row.condition,
                "training_round": row.training_round, "n_participating_hospitals": len(row.participating_hospitals or []),
                "artifact_hash": row.artifact_hash, "metrics": {k: row.metrics.get(k) for k in
                                                                ("accuracy", "n_eval", "majority_class_floor", "eval_set")},
                "training_metadata": row.training_metadata, "validation_status": row.validation_status,
                "deployment_status": row.deployment_status, "approved_at": row.approved_at,
                "parameters": row.parameters, "input_spec": row.input_spec}

    @router.get("/admin/models/current", response_model=ModelVersionOut)
    def current_model(model_name: str, condition: str, db: Session = Depends(get_db),
                      _=Depends(require_super_admin)):
        cur = _current(db, model_name, condition)
        if cur is None:
            raise HTTPException(status_code=404, detail="No deployed model for this condition")
        return cur

    return router

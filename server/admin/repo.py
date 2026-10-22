"""
Module 7 data access (training rounds, validation-flag summaries, model
registry). Endpoints no longer build queries; they call this class.

Composite indexes for the ordered queries are declared in
firestore.indexes.json at the repo root.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

import models
from docstore import AlreadyExists, Backend, from_doc, to_doc


def _many(cls, rows):
    return [from_doc(cls, r) for r in rows]


class Repo:
    def __init__(self, backend: Backend):
        self.b = backend

    # ---------------------------------------------------------- training rounds
    def add_round(self, r: models.TrainingRound) -> models.TrainingRound:
        self.b.create(models.TrainingRound.COLLECTION, r.id, to_doc(r))
        return r

    def list_rounds(self, limit: int) -> list[models.TrainingRound]:
        rows = self.b.query(models.TrainingRound.COLLECTION, order_by="round_number", descending=True, limit=limit)
        return _many(models.TrainingRound, rows)

    def count_rounds(self) -> int:
        return self.b.count(models.TrainingRound.COLLECTION)

    # ------------------------------------------------------ gated retraining queue
    def consider_retraining(self, hospital_id: str, eligible_records: int, threshold: int) -> tuple[str, str | None]:
        """Use new eligible records since the last completed runner request."""
        if threshold < 1:
            raise ValueError("retraining threshold must be positive")
        progress_id = hashlib.sha256(hospital_id.encode()).hexdigest()
        progress = self.b.get(models.RetrainingProgress.COLLECTION, progress_id)
        if progress is None:
            initial = models.RetrainingProgress(
                hospital_id=hospital_id, last_completed_records=eligible_records,
                latest_eligible_records=eligible_records,
            )
            try:
                self.b.create(models.RetrainingProgress.COLLECTION, progress_id, to_doc(initial))
                return "baseline_initialized", None
            except AlreadyExists:
                progress = self.b.get(models.RetrainingProgress.COLLECTION, progress_id)
                if progress is None:
                    raise

        active = next((row for row in self.list_retraining(hospital_id, 100)
                       if row.status in {"PENDING", "CLAIMED"}), None)
        lock = self.b.get("retraining_active_locks", progress_id)
        if active is not None or lock is not None:
            active_id = active.id if active is not None else lock["request_id"]
            self.b.update(models.RetrainingProgress.COLLECTION, progress_id,
                          {"latest_eligible_records": eligible_records,
                           "updated_at": models.utcnow()})
            return "already_queued", active_id

        baseline = int(progress["last_completed_records"])
        if eligible_records < baseline:
            self.b.update(models.RetrainingProgress.COLLECTION, progress_id,
                          {"last_completed_records": eligible_records,
                           "latest_eligible_records": eligible_records,
                           "updated_at": models.utcnow()})
            return "below_threshold", None
        bucket = (eligible_records - baseline) // threshold
        if bucket < 1:
            self.b.update(models.RetrainingProgress.COLLECTION, progress_id,
                          {"latest_eligible_records": eligible_records,
                           "updated_at": models.utcnow()})
            return "below_threshold", None

        request_id = hashlib.sha256(f"{hospital_id}:{baseline}:{bucket}".encode()).hexdigest()
        request = models.RetrainingRequest(
            id=request_id, hospital_id=hospital_id, eligible_records=eligible_records,
            threshold_bucket=bucket, baseline_records=baseline,
        )
        try:
            self.b.commit([
                ("create", models.RetrainingRequest.COLLECTION, request.id, to_doc(request)),
                ("create", "retraining_active_locks", progress_id,
                 {"hospital_id": hospital_id, "request_id": request.id}),
                ("update", models.RetrainingProgress.COLLECTION, progress_id,
                 {"latest_eligible_records": eligible_records, "updated_at": models.utcnow()}),
            ])
        except AlreadyExists:
            lock = self.b.get("retraining_active_locks", progress_id)
            if lock is not None:
                return "already_queued", lock["request_id"]
            return "already_fired", request_id
        return "queued", request_id

    def list_retraining(self, hospital_id: Optional[str] = None, limit: int = 100) -> list[models.RetrainingRequest]:
        filters = [("hospital_id", "==", hospital_id)] if hospital_id else []
        rows = self.b.query(models.RetrainingRequest.COLLECTION, filters, order_by="created_at",
                            descending=True, limit=limit)
        return _many(models.RetrainingRequest, rows)

    def get_retraining(self, request_id: str) -> Optional[models.RetrainingRequest]:
        return from_doc(models.RetrainingRequest,
                        self.b.get(models.RetrainingRequest.COLLECTION, request_id))

    def claim_retraining(self, hospital_id: str) -> Optional[models.RetrainingRequest]:
        """Atomically claim one request; only one runner can win a request."""
        for request in self.list_retraining(hospital_id, limit=100):
            if request.status != "PENDING":
                continue
            claim_id = request.id
            now = models.utcnow()
            request.status = "CLAIMED"
            request.claimed_at = now
            try:
                self.b.commit([
                    ("create", "retraining_request_claims", claim_id,
                     {"request_id": request.id, "hospital_id": hospital_id, "claimed_at": now}),
                    ("update", models.RetrainingRequest.COLLECTION, request.id,
                     {"status": request.status, "claimed_at": request.claimed_at}),
                ])
            except AlreadyExists:
                continue
            return request
        return None

    def complete_retraining(self, request_id: str, hospital_id: str, status: str,
                            eligible_records: int | None) -> Optional[models.RetrainingRequest]:
        request = self.get_retraining(request_id)
        if request is None or request.hospital_id != hospital_id or request.status != "CLAIMED":
            return None
        if status == "COMPLETED" and not request.candidate_id:
            return None
        request.status = status
        request.completed_at = models.utcnow()
        progress_id = hashlib.sha256(hospital_id.encode()).hexdigest()
        progress = self.b.get(models.RetrainingProgress.COLLECTION, progress_id)
        completion_count = (eligible_records if eligible_records is not None
                            else int(progress["latest_eligible_records"]))
        operations = [
                    ("create", "retraining_request_completions", request.id,
                     {"request_id": request.id, "hospital_id": hospital_id, "status": status,
                      "completed_at": request.completed_at}),
                    ("update", models.RetrainingRequest.COLLECTION, request.id,
                     {"status": request.status, "completed_at": request.completed_at}),
                    ("delete", "retraining_active_locks", progress_id),
            ]
        if status == "COMPLETED":
            operations.append(("update", models.RetrainingProgress.COLLECTION, progress_id,
                 {"last_completed_records": completion_count,
                  "latest_eligible_records": completion_count,
                  "updated_at": request.completed_at}))
        else:
            operations.append(("update", models.RetrainingProgress.COLLECTION, progress_id,
                                   {"latest_eligible_records": completion_count,
                                    "updated_at": request.completed_at}))
        try:
            self.b.commit(operations)
        except AlreadyExists:
            return None
        return request

    # ----------------------------------------------------------- validation flags
    def add_flag(self, f: models.ValidationFlag) -> models.ValidationFlag:
        self.b.create(models.ValidationFlag.COLLECTION, f.id, to_doc(f))
        return f

    def list_flags(self, hospital_id: Optional[str], limit: int) -> list[models.ValidationFlag]:
        filters = [("hospital_id", "==", hospital_id)] if hospital_id else []
        rows = self.b.query(models.ValidationFlag.COLLECTION, filters, order_by="reported_at",
                            descending=True, limit=limit)
        return _many(models.ValidationFlag, rows)

    def count_flags(self, since: Optional[datetime] = None) -> int:
        filters = [("reported_at", ">=", since)] if since else []
        return self.b.count(models.ValidationFlag.COLLECTION, filters)

    # ------------------------------------------------------------ model registry
    def add_model(self, m: models.ModelVersion) -> models.ModelVersion:
        request_ids = m.training_metadata.get("retraining_request_ids", [])
        if not request_ids:
            self.b.create(models.ModelVersion.COLLECTION, m.id, to_doc(m))
            return m

        operations = [("create", models.ModelVersion.COLLECTION, m.id, to_doc(m))]
        for request_id in request_ids:
            request = self.get_retraining(request_id)
            if request is None or request.status != "CLAIMED" or request.candidate_id:
                raise ValueError(f"retraining request {request_id!r} is not claimable for candidate linkage")
            operations.extend([
                ("create", "retraining_candidate_links", request_id,
                 {"request_id": request_id, "candidate_id": m.id, "hospital_id": request.hospital_id}),
                ("update", models.RetrainingRequest.COLLECTION, request_id, {"candidate_id": m.id}),
            ])
        self.b.commit(operations)
        return m

    def get_model(self, model_id: str) -> Optional[models.ModelVersion]:
        return from_doc(models.ModelVersion, self.b.get(models.ModelVersion.COLLECTION, model_id))

    def save_models(self, *rows: models.ModelVersion) -> None:
        """Write one or more model versions in ONE atomic commit (promotion and
        rollback change two rows that must never be seen half-updated)."""
        self.b.commit([("set", models.ModelVersion.COLLECTION, m.id, to_doc(m)) for m in rows])

    def count_versions(self, model_name: str, condition: str) -> int:
        return self.b.count(models.ModelVersion.COLLECTION,
                            [("model_name", "==", model_name), ("condition", "==", condition)])

    def get_deployed(self, model_name: str, condition: str) -> Optional[models.ModelVersion]:
        rows = self.b.query(models.ModelVersion.COLLECTION,
                            [("model_name", "==", model_name), ("condition", "==", condition),
                             ("deployment_status", "==", "DEPLOYED")], limit=1)
        return from_doc(models.ModelVersion, rows[0]) if rows else None

    def list_models(self, condition: Optional[str], limit: int = 200) -> list[models.ModelVersion]:
        filters = [("condition", "==", condition)] if condition else []
        rows = self.b.query(models.ModelVersion.COLLECTION, filters, order_by="created_at",
                            descending=True, limit=limit)
        return _many(models.ModelVersion, rows)

    def get_promoted(self, condition: str, model_name: Optional[str] = None) -> Optional[models.ModelVersion]:
        """Newest-approved DEPLOYED model for a condition (there is normally exactly one per name)."""
        filters = [("condition", "==", condition), ("deployment_status", "==", "DEPLOYED")]
        if model_name:
            filters.append(("model_name", "==", model_name))
        rows = _many(models.ModelVersion, self.b.query(models.ModelVersion.COLLECTION, filters))
        rows.sort(key=lambda m: m.approved_at or datetime.min.replace(tzinfo=models.utcnow().tzinfo), reverse=True)
        return rows[0] if rows else None

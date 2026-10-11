"""
Module 1 data access. Every read/write the service performs goes through this
class — endpoints no longer build queries.

Tenancy rule (unchanged): callers pass the hospital_id they got from the JWT,
and every list/count/export below is filtered by it. Lookups by id
(`get_case`, `get_vitals`, ...) return the document whichever hospital owns it,
so the endpoint can answer 404 vs 403 and audit the cross-tenant attempt exactly
as before; endpoints compare hospital_id themselves.

Uniqueness without unique constraints: `user_emails` and `hospital_names` hold
one tiny document per taken value (id = sha256 of the value), created in the
same atomic commit as the entity. A concurrent duplicate loses with
DuplicateError instead of silently creating a second row.

Composite indexes the ordered queries need are declared in
firestore.indexes.json at the repo root.
"""
from __future__ import annotations

import hashlib
from typing import Optional

import models
from docstore import AlreadyExists, Backend, from_doc, to_doc


class DuplicateError(Exception):
    """A unique value (user e-mail, hospital name) is already taken."""


def _key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _many(cls, rows):
    return [from_doc(cls, r) for r in rows]


class Repo:
    def __init__(self, backend: Backend):
        self.b = backend

    # ---------------------------------------------------------------- hospitals
    def create_hospital(self, h: models.Hospital) -> models.Hospital:
        try:
            self.b.commit([
                ("create", "hospital_names", _key(h.name), {"hospital_id": h.id}),
                ("create", models.Hospital.COLLECTION, h.id, to_doc(h)),
            ])
        except AlreadyExists as exc:
            raise DuplicateError("hospital name") from exc
        return h

    def get_hospital(self, hospital_id: Optional[str]) -> Optional[models.Hospital]:
        if not hospital_id:
            return None
        return from_doc(models.Hospital, self.b.get(models.Hospital.COLLECTION, hospital_id))

    def get_hospital_by_name(self, name: str) -> Optional[models.Hospital]:
        idx = self.b.get("hospital_names", _key(name))
        return self.get_hospital(idx["hospital_id"]) if idx else None

    def list_hospitals(self, only_id: Optional[str] = None) -> list[models.Hospital]:
        if only_id is not None:
            h = self.get_hospital(only_id)
            return [h] if h else []
        return _many(models.Hospital, self.b.query(models.Hospital.COLLECTION))

    def save_hospital(self, h: models.Hospital) -> models.Hospital:
        self.b.set(models.Hospital.COLLECTION, h.id, to_doc(h))
        return h

    # -------------------------------------------------------------------- users
    def create_user(self, u: models.User) -> models.User:
        try:
            self.b.commit([
                ("create", "user_emails", _key(u.email), {"user_id": u.id}),
                ("create", models.User.COLLECTION, u.id, to_doc(u)),
            ])
        except AlreadyExists as exc:
            raise DuplicateError("email") from exc
        return u

    def get_user(self, user_id: Optional[str]) -> Optional[models.User]:
        if not user_id:
            return None
        return from_doc(models.User, self.b.get(models.User.COLLECTION, user_id))

    def get_user_by_email(self, email: str) -> Optional[models.User]:
        idx = self.b.get("user_emails", _key(email))
        return self.get_user(idx["user_id"]) if idx else None

    def save_user(self, u: models.User) -> models.User:
        self.b.set(models.User.COLLECTION, u.id, to_doc(u))
        return u

    def list_doctors(self, hospital_id: str) -> list[models.User]:
        rows = self.b.query(models.User.COLLECTION, [("hospital_id", "==", hospital_id),
                                                     ("role", "==", models.Role.CLINICIAN.value)])
        return sorted(_many(models.User, rows), key=lambda u: u.created_at)

    # ------------------------------------------------------------------- vitals
    def add_vitals(self, rec: models.VitalsRecord) -> models.VitalsRecord:
        self.add_vitals_bulk([rec])
        return rec

    def add_vitals_bulk(self, recs: list[models.VitalsRecord]) -> None:
        """Chunked into <=450-write batches: a very large upload is not atomic across chunks."""
        docs = []
        for r in recs:
            r.has_label = r.label is not None
            docs.append((r.id, to_doc(r)))
        if docs:
            self.b.bulk_set(models.VitalsRecord.COLLECTION, docs)

    def get_vitals(self, record_id: str) -> Optional[models.VitalsRecord]:
        return from_doc(models.VitalsRecord, self.b.get(models.VitalsRecord.COLLECTION, record_id))

    def save_vitals(self, rec: models.VitalsRecord) -> models.VitalsRecord:
        rec.has_label = rec.label is not None
        self.b.set(models.VitalsRecord.COLLECTION, rec.id, to_doc(rec))
        return rec

    def delete_vitals(self, record_id: str) -> None:
        self.b.delete(models.VitalsRecord.COLLECTION, record_id)

    def list_vitals(self, hospital_id: str, validation_status: Optional[str] = None,
                    limit: int = 100) -> list[models.VitalsRecord]:
        filters = [("hospital_id", "==", hospital_id)]
        if validation_status:
            filters.append(("validation_status", "==", validation_status))
        rows = self.b.query(models.VitalsRecord.COLLECTION, filters, order_by="patient_ref", limit=limit)
        return _many(models.VitalsRecord, rows)

    def list_flagged(self, hospital_id: str) -> list[models.VitalsRecord]:
        rows = self.b.query(models.VitalsRecord.COLLECTION, [("hospital_id", "==", hospital_id),
                                                             ("validation_status", "==", "flagged")])
        return _many(models.VitalsRecord, rows)

    def export_vitals(self, hospital_id: str, include_flagged: bool, labeled_only: bool) -> list[models.VitalsRecord]:
        filters = [("hospital_id", "==", hospital_id)]
        if not include_flagged:
            filters.append(("validation_status", "==", "passed"))
        if labeled_only:
            filters.append(("has_label", "==", True))
        return _many(models.VitalsRecord, self.b.query(models.VitalsRecord.COLLECTION, filters))

    def list_case_vitals(self, case_id: str, hospital_id: str) -> list[models.VitalsRecord]:
        rows = self.b.query(models.VitalsRecord.COLLECTION,
                            [("case_id", "==", case_id), ("hospital_id", "==", hospital_id)],
                            order_by="uploaded_at", descending=True)
        return _many(models.VitalsRecord, rows)

    def count_vitals(self, hospital_id: str, labeled_only: bool = False) -> int:
        filters = [("hospital_id", "==", hospital_id)]
        if labeled_only:
            filters.append(("has_label", "==", True))
        return self.b.count(models.VitalsRecord.COLLECTION, filters)

    def last_upload(self, hospital_id: str):
        rows = self.b.query(models.VitalsRecord.COLLECTION, [("hospital_id", "==", hospital_id)],
                            order_by="uploaded_at", descending=True, limit=1)
        return rows[0]["uploaded_at"] if rows else None

    # -------------------------------------------------------------------- cases
    def add_case(self, c: models.Case) -> models.Case:
        self.b.create(models.Case.COLLECTION, c.id, to_doc(c))
        return c

    def get_case(self, case_id: str) -> Optional[models.Case]:
        return from_doc(models.Case, self.b.get(models.Case.COLLECTION, case_id))

    def save_case(self, c: models.Case) -> models.Case:
        c.updated_at = models.utcnow()
        self.b.set(models.Case.COLLECTION, c.id, to_doc(c))
        return c

    def list_cases(self, hospital_id: str, limit: int = 100) -> list[models.Case]:
        rows = self.b.query(models.Case.COLLECTION, [("hospital_id", "==", hospital_id)],
                            order_by="created_at", descending=True, limit=limit)
        return _many(models.Case, rows)

    # ---------------------------------------------------------- medical history
    def get_history(self, case_id: str) -> Optional[models.MedicalHistory]:
        return from_doc(models.MedicalHistory, self.b.get(models.MedicalHistory.COLLECTION, case_id))

    def save_history(self, h: models.MedicalHistory) -> models.MedicalHistory:
        """Upsert. The document id is the case id: one history per case, structurally."""
        h.updated_at = models.utcnow()
        self.b.set(models.MedicalHistory.COLLECTION, h.case_id, to_doc(h))
        return h

    # ------------------------------------------------------------------ reviews
    def add_review(self, review: models.ClinicianReview, case: models.Case, new_status: str) -> None:
        """Insert the review and move the case's status in ONE atomic commit."""
        case.status = new_status
        case.updated_at = models.utcnow()
        self.b.commit([
            ("create", models.ClinicianReview.COLLECTION, review.id, to_doc(review)),
            ("update", models.Case.COLLECTION, case.id, {"status": case.status, "updated_at": case.updated_at}),
        ])

    def list_reviews(self, case_id: str, hospital_id: str) -> list[models.ClinicianReview]:
        rows = self.b.query(models.ClinicianReview.COLLECTION,
                            [("case_id", "==", case_id), ("hospital_id", "==", hospital_id)],
                            order_by="created_at")
        return _many(models.ClinicianReview, rows)

    # --------------------------------------------------------------- analyses
    def add_analysis(self, analysis: models.AIAnalysis) -> models.AIAnalysis:
        """Create only; analysis records have no update or delete operation."""
        self.b.create(models.AIAnalysis.COLLECTION, analysis.id, to_doc(analysis))
        return analysis

    def get_analysis(self, analysis_id: str) -> Optional[models.AIAnalysis]:
        return from_doc(models.AIAnalysis, self.b.get(models.AIAnalysis.COLLECTION, analysis_id))

    def list_analyses(self, case_id: str, hospital_id: str) -> list[models.AIAnalysis]:
        rows = self.b.query(models.AIAnalysis.COLLECTION,
                            [("case_id", "==", case_id), ("hospital_id", "==", hospital_id)],
                            order_by="created_at", descending=True)
        return _many(models.AIAnalysis, rows)

    # -------------------------------------------------------------------- scans
    def add_scan(self, s: models.Scan) -> models.Scan:
        self.b.create(models.Scan.COLLECTION, s.id, to_doc(s))
        return s

    def list_scans(self, case_id: str, hospital_id: str) -> list[models.Scan]:
        rows = self.b.query(models.Scan.COLLECTION,
                            [("case_id", "==", case_id), ("hospital_id", "==", hospital_id)],
                            order_by="created_at")
        return _many(models.Scan, rows)

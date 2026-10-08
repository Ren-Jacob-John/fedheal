import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Enum, ForeignKey, Boolean, Float, Integer, DateTime, JSON, Text, Index
from sqlalchemy.orm import relationship

from database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Role(str, enum.Enum):
    SUPER_ADMIN = "super_admin"   # you, the platform operator — manages global model
    HOSPITAL_ADMIN = "hospital_admin"  # manages that hospital's users/data
    CLINICIAN = "clinician"       # views predictions, uploads cases


class Hospital(Base):
    """
    One row per tenant. This is the unit of data isolation: every other table
    in the system is scoped by hospital_id, and a hospital's own model/data
    is never visible to another hospital_id.
    """
    __tablename__ = "hospitals"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, default=True)

    # Sprint A: does this hospital have real clinical outcome labels to
    # supply? When True, uploads missing a `label` are REJECTED (Module 2's
    # rules.check_required_label) instead of stored unlabeled and later
    # placeholder-labeled at training time.
    #
    # Defaults False, which preserves the pre-Sprint-A behaviour for every
    # existing tenant — this is an explicit per-hospital declaration
    # ("we have outcomes, hold us to them"), not something to infer from
    # whether labels happen to show up in an upload. Inferring it would make
    # the rule silently switch itself off the first time a hospital's export
    # broke, which is the exact failure this is meant to catch.
    requires_label = Column(Boolean, nullable=False, default=False)

    users = relationship("User", back_populates="hospital")


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=gen_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(Enum(Role), nullable=False, default=Role.CLINICIAN)

    # Nullable only for SUPER_ADMIN, who isn't tied to one hospital.
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=True)
    hospital = relationship("Hospital", back_populates="users")

    # P0 doctor management. `is_active` lets a hospital admin disable a
    # doctor without deleting their audit trail; a disabled account can
    # neither log in nor use an already-issued token (see main.get_current_user).
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class VitalsRecord(Base):
    """
    One row per uploaded vitals record that PASSED Module 2's hard checks
    (schema/range/consistency) — rejected records are never stored here at
    all, only reported back in the upload response. Records that were
    merely FLAGGED (soft outlier) are stored too, tagged accordingly, so a
    hospital admin can review them later; Module 3's real-data loader only
    trains on validation_status == "passed" by default.

    This is the table that turns "Module 2 validated it" into "Module 3 can
    actually train on it" — the missing link both modules' READMEs called
    out as next-sprint work. hospital_id scoping follows the same rule as
    every other table here: pulled from the JWT, never trusted from the
    request body.
    """
    __tablename__ = "vitals_records"

    id = Column(String, primary_key=True, default=gen_uuid)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=False, index=True)
    # Optional link to a patient Case. Legacy bulk uploads (no case) keep
    # working unchanged; vitals entered through POST /cases/{id}/vitals carry it.
    case_id = Column(String, ForeignKey("cases.id"), nullable=True, index=True)

    patient_ref = Column(String, nullable=False)
    age_years = Column(Float, nullable=False)
    height_cm = Column(Float, nullable=False)
    weight_kg = Column(Float, nullable=False)
    systolic_bp = Column(Float, nullable=True)
    diastolic_bp = Column(Float, nullable=True)
    heart_rate_bpm = Column(Float, nullable=True)
    medication_count = Column(Integer, nullable=False, default=0)
    medication_mg_total = Column(Float, nullable=False, default=0)

    # Optional diagnosis/outcome label (0/1) for supervised training. Real
    # deployments would populate this from the hospital's actual clinical
    # outcome, not upload-time guesswork — see module3-fedlearning's
    # real_data.py docstring for how the loader handles records that don't
    # have one yet.
    label = Column(Integer, nullable=True)

    # Sprint A: where that label came from. Only ever one of:
    #   "hospital" — a real clinical outcome the hospital uploaded.
    #   "missing"  — no label supplied (only possible when the hospital is
    #                NOT configured with requires_label).
    #
    # There is deliberately no "placeholder" value. Module 3's rule-based
    # placeholder label is computed at training time and never written
    # back here, so this column can't ever assert that a made-up label is
    # a clinical fact. A record that reads label=1/label_source="hospital"
    # means a clinician's system said so, full stop — which is what makes
    # this column worth having at all.
    label_source = Column(String, nullable=False, default="missing")

    validation_status = Column(String, nullable=False, default="passed")  # "passed" | "flagged"
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CaseStatus(str, enum.Enum):
    OPEN = "OPEN"
    REVIEWED = "REVIEWED"
    NEEDS_MORE_DATA = "NEEDS_MORE_DATA"


class Case(Base):
    """
    A patient case / encounter: the parent of vitals, medical history and
    clinician reviews. hospital_id comes from the creating doctor's JWT,
    never from the request body. `patient_ref` is a synthetic/internal
    reference (e.g. PAT-DEMO-001), not a real identity.
    """
    __tablename__ = "cases"

    id = Column(String, primary_key=True, default=gen_uuid)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=False, index=True)
    patient_ref = Column(String, nullable=False, index=True)
    encounter_id = Column(String, nullable=False, default=gen_uuid)
    admission_reason = Column(String, nullable=False)
    current_condition = Column(String, nullable=True)   # a Module 6 condition key, e.g. "heart_disease"
    presenting_symptoms = Column(JSON, nullable=False, default=list)
    status = Column(String, nullable=False, default=CaseStatus.OPEN.value)
    created_by = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (Index("ix_cases_hospital_created", "hospital_id", "created_at"),)


class MedicalHistory(Base):
    """One structured history per case (upserted). Lists of short strings;
    only fields the MVP use case justifies."""
    __tablename__ = "medical_histories"

    id = Column(String, primary_key=True, default=gen_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, unique=True, index=True)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=False, index=True)
    conditions = Column(JSON, nullable=False, default=list)
    previous_diagnoses = Column(JSON, nullable=False, default=list)
    surgeries = Column(JSON, nullable=False, default=list)
    allergies = Column(JSON, nullable=False, default=list)
    medications = Column(JSON, nullable=False, default=list)
    family_history = Column(JSON, nullable=False, default=list)
    previous_admissions = Column(JSON, nullable=False, default=list)
    symptoms = Column(JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class ClinicianReview(Base):
    """A doctor's decision on an AI result. Never used as a training label."""
    __tablename__ = "clinician_reviews"

    id = Column(String, primary_key=True, default=gen_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=False, index=True)
    doctor_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    decision = Column(String, nullable=False)   # ACCEPTED | OVERRIDDEN | NEEDS_MORE_DATA
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class Scan(Base):
    """
    Metadata for an uploaded image linked to a case. The file itself lives under UPLOAD_STORAGE_PATH
    with a server-generated name; the client's filename is never used as a path.
    status: UPLOADED = stored and linked, NO analysis exists for it (there is no validated imaging model).
    """
    __tablename__ = "scans"

    id = Column(String, primary_key=True, default=gen_uuid)
    case_id = Column(String, ForeignKey("cases.id"), nullable=False, index=True)
    hospital_id = Column(String, ForeignKey("hospitals.id"), nullable=False, index=True)
    scan_type = Column(String, nullable=False)          # free label chosen from a fixed list, e.g. "chest_xray"
    file_reference = Column(String, nullable=False)     # server-side relative path; never returned to clients
    content_type = Column(String, nullable=False)       # sniffed from the bytes, not trusted from the client
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String, nullable=False)
    status = Column(String, nullable=False, default="UPLOADED")
    uploaded_by = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

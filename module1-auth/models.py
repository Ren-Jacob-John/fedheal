"""
Entities stored in Firestore (one collection per entity — see COLLECTION).

These used to be SQLAlchemy tables. They are now plain dataclasses: attribute
access (`user.role`, `case.hospital_id`) and pydantic `from_attributes=True`
responses work exactly as before. Mapping to/from Firestore documents lives in
docstore.to_doc / from_doc; all reads and writes go through repo.py.

What Firestore does NOT give you (and how each is handled):
  * foreign keys      -> hospital_id / case_id / user_id are plain string
                         references. repo.py never writes a child whose parent
                         the endpoint hasn't just loaded, and every query is
                         still scoped by hospital_id (tenancy is enforced in
                         application code, as before — see cases.py).
  * unique columns    -> hospitals.name, users.email: repo.py writes a small
                         "index document" atomically with the entity
                         (collections hospital_names / user_emails).
                         medical_histories uses case_id as the document id,
                         which makes "one history per case" structural.
  * auto-update stamp -> repo.py sets updated_at on every save.
"""
import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from docstore import blob_field, enum_field


def gen_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    SUPER_ADMIN = "super_admin"   # you, the platform operator — manages global model
    HOSPITAL_ADMIN = "hospital_admin"  # manages that hospital's users/data
    CLINICIAN = "clinician"       # views predictions, uploads cases


class CaseStatus(str, enum.Enum):
    OPEN = "OPEN"
    REVIEWED = "REVIEWED"
    NEEDS_MORE_DATA = "NEEDS_MORE_DATA"


@dataclass(kw_only=True)
class Hospital:
    """
    One document per tenant. This is the unit of data isolation: every other
    collection in the system is scoped by hospital_id, and a hospital's own
    model/data is never visible to another hospital_id.

    `requires_label` (Sprint A): does this hospital have real clinical outcome
    labels to supply? When True, uploads missing a `label` are REJECTED (Module
    2's rules.check_required_label) instead of stored unlabeled. Defaults False;
    it is an explicit per-hospital declaration, never inferred from uploads.
    """
    COLLECTION = "hospitals"

    id: str = field(default_factory=gen_uuid)
    name: str
    is_active: bool = True
    requires_label: bool = False


@dataclass(kw_only=True)
class User:
    COLLECTION = "users"

    id: str = field(default_factory=gen_uuid)
    email: str
    hashed_password: str
    role: Role = enum_field(Role, default=Role.CLINICIAN)
    # None only for SUPER_ADMIN, who isn't tied to one hospital.
    hospital_id: Optional[str] = None
    # `is_active` lets a hospital admin disable a doctor without deleting their
    # audit trail; a disabled account can neither log in nor use an issued token.
    full_name: Optional[str] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=utcnow)


@dataclass(kw_only=True)
class VitalsRecord:
    """
    One document per uploaded vitals record that PASSED Module 2's hard checks.
    Rejected records are never stored; FLAGGED ones are, tagged accordingly.
    hospital_id comes from the JWT, never from the request body.

    label_source is only ever "hospital" (a real clinical outcome the hospital
    uploaded) or "missing". There is deliberately no "placeholder" value:
    Module 3's rule-based placeholder label is computed at training time and
    never written back here.
    """
    COLLECTION = "vitals_records"

    id: str = field(default_factory=gen_uuid)
    hospital_id: str
    case_id: Optional[str] = None   # legacy bulk uploads carry no case

    patient_ref: str
    age_years: float
    height_cm: float
    weight_kg: float
    systolic_bp: Optional[float] = None
    diastolic_bp: Optional[float] = None
    heart_rate_bpm: Optional[float] = None
    temperature_c: Optional[float] = None
    spo2_percent: Optional[float] = None
    respiratory_rate_bpm: Optional[float] = None
    medication_count: int = 0
    medication_mg_total: float = 0
    label: Optional[int] = None
    label_source: str = "missing"
    validation_status: str = "passed"  # "passed" | "flagged"
    uploaded_at: datetime = field(default_factory=utcnow)
    # Derived from `label`, stored so "labelled records only" is a cheap equality
    # query (Firestore has no cheap IS NOT NULL). Always recomputed on write.
    has_label: bool = False

    def __post_init__(self):
        self.has_label = self.label is not None


@dataclass(kw_only=True)
class Case:
    """
    A patient case / encounter: the parent of vitals, medical history and
    clinician reviews. hospital_id comes from the creating doctor's JWT.
    `patient_ref` is a synthetic/internal reference, not a real identity.
    """
    COLLECTION = "cases"

    id: str = field(default_factory=gen_uuid)
    hospital_id: str
    patient_ref: str
    encounter_id: str = field(default_factory=gen_uuid)
    admission_reason: str
    current_condition: Optional[str] = None   # a Module 6 condition key, e.g. "heart_disease"
    presenting_symptoms: list = field(default_factory=list)
    status: str = CaseStatus.OPEN.value
    created_by: str
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass(kw_only=True)
class MedicalHistory:
    """One structured history per case (upserted). Stored under the document id
    == case_id, so a second history for the same case cannot exist."""
    COLLECTION = "medical_histories"

    id: str = field(default_factory=gen_uuid)
    case_id: str
    hospital_id: str
    conditions: list = field(default_factory=list)
    previous_diagnoses: list = field(default_factory=list)
    surgeries: list = field(default_factory=list)
    allergies: list = field(default_factory=list)
    medications: list = field(default_factory=list)
    family_history: list = field(default_factory=list)
    previous_admissions: list = field(default_factory=list)
    symptoms: list = field(default_factory=list)
    notes: Optional[str] = None
    created_by: str
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass(kw_only=True)
class AIAnalysis:
    """Append-only, hospital-scoped structured decision-support output."""
    COLLECTION = "ai_analyses"

    id: str = field(default_factory=gen_uuid)
    hospital_id: str
    case_id: str
    model_version: str
    model_status: str
    artifact_hash: Optional[str] = None
    inputs_used: list = blob_field(default_factory=list)
    missing_inputs: list = blob_field(default_factory=list)
    output: dict = blob_field(default_factory=dict)
    created_by: str
    created_at: datetime = field(default_factory=utcnow)


@dataclass(kw_only=True)
class ClinicianReview:
    """A doctor's decision on an AI result. Never used as a training label."""
    COLLECTION = "clinician_reviews"

    id: str = field(default_factory=gen_uuid)
    case_id: str
    hospital_id: str
    doctor_id: str
    decision: str   # ACCEPTED | OVERRIDDEN | NEEDS_MORE_DATA
    analysis_id: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime = field(default_factory=utcnow)


@dataclass(kw_only=True)
class Scan:
    """
    Metadata for an uploaded image linked to a case. The file itself lives under
    UPLOAD_STORAGE_PATH with a server-generated name; the client's filename is
    never used as a path. status UPLOADED = stored and linked, NO analysis exists
    for it (there is no validated imaging model).
    """
    COLLECTION = "scans"

    id: str = field(default_factory=gen_uuid)
    case_id: str
    hospital_id: str
    scan_type: str          # free label chosen from a fixed list, e.g. "chest_xray"
    file_reference: str     # server-side relative path; never returned to clients
    content_type: str       # sniffed from the bytes, not trusted from the client
    size_bytes: int
    sha256: str
    status: str = "UPLOADED"
    uploaded_by: str
    created_at: datetime = field(default_factory=utcnow)

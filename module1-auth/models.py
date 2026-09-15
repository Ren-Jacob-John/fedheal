import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Enum, ForeignKey, Boolean, Float, Integer, DateTime
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

import enum
import uuid

from sqlalchemy import Column, String, Enum, ForeignKey, Boolean
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

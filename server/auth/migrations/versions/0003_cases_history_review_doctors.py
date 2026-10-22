"""P0: patient cases, medical history, clinician reviews, doctor management

Revision ID: 0003_cases_history_review_doctors
Revises: 0002_label_provenance
Create Date: 2026-10-06

Additive only. Existing users are backfilled is_active=true; vitals_records
gets a nullable case_id so legacy bulk uploads keep working untouched.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_cases_history_review_doctors"
down_revision = "0002_label_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("full_name", sa.String(), nullable=True))
        b.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        b.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))

    op.create_table(
        "cases",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("hospital_id", sa.String(), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column("patient_ref", sa.String(), nullable=False),
        sa.Column("encounter_id", sa.String(), nullable=False),
        sa.Column("admission_reason", sa.String(), nullable=False),
        sa.Column("current_condition", sa.String(), nullable=True),
        sa.Column("presenting_symptoms", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_cases_hospital_id", "cases", ["hospital_id"])
    op.create_index("ix_cases_patient_ref", "cases", ["patient_ref"])
    op.create_index("ix_cases_created_by", "cases", ["created_by"])
    op.create_index("ix_cases_created_at", "cases", ["created_at"])
    op.create_index("ix_cases_hospital_created", "cases", ["hospital_id", "created_at"])

    op.create_table(
        "medical_histories",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("hospital_id", sa.String(), sa.ForeignKey("hospitals.id"), nullable=False),
        *[sa.Column(c, sa.JSON(), nullable=False) for c in (
            "conditions", "previous_diagnoses", "surgeries", "allergies", "medications",
            "family_history", "previous_admissions", "symptoms")],
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_medical_histories_case_id", "medical_histories", ["case_id"], unique=True)
    op.create_index("ix_medical_histories_hospital_id", "medical_histories", ["hospital_id"])

    op.create_table(
        "clinician_reviews",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("hospital_id", sa.String(), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column("doctor_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    for col in ("case_id", "hospital_id", "doctor_id", "created_at"):
        op.create_index(f"ix_clinician_reviews_{col}", "clinician_reviews", [col])

    with op.batch_alter_table("vitals_records") as b:
        b.add_column(sa.Column("case_id", sa.String(), nullable=True))
        b.create_foreign_key("fk_vitals_case", "cases", ["case_id"], ["id"])
        b.create_index("ix_vitals_records_case_id", ["case_id"])


def downgrade() -> None:
    with op.batch_alter_table("vitals_records") as b:
        b.drop_index("ix_vitals_records_case_id")
        b.drop_constraint("fk_vitals_case", type_="foreignkey")
        b.drop_column("case_id")
    op.drop_table("clinician_reviews")
    op.drop_table("medical_histories")
    op.drop_table("cases")
    with op.batch_alter_table("users") as b:
        b.drop_column("created_at")
        b.drop_column("is_active")
        b.drop_column("full_name")

"""Module 7 baseline: training_rounds, validation_flags, model_versions

Revision ID: 0001_admin_baseline
Revises:
Create Date: 2026-10-07

Idempotent on purpose: deployments that were created by the old
Base.metadata.create_all() already have training_rounds / validation_flags;
those tables are left alone (and adopted by this revision), missing ones are created.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_admin_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _missing(name: str) -> bool:
    return name not in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _missing("training_rounds"):
        op.create_table(
            "training_rounds",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("round_number", sa.Integer(), nullable=False),
            sa.Column("n_hospitals", sa.Integer(), nullable=False),
            sa.Column("global_accuracy", sa.Float(), nullable=True),
            sa.Column("baseline_accuracy", sa.Float(), nullable=True),
            sa.Column("notes", sa.String(), nullable=True),
            sa.Column("reported_at", sa.DateTime(), nullable=True),
        )
    if _missing("validation_flags"):
        op.create_table(
            "validation_flags",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("hospital_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("reason", sa.String(), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False),
            sa.Column("reported_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_validation_flags_hospital_id", "validation_flags", ["hospital_id"])
    if _missing("model_versions"):
        op.create_table(
            "model_versions",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("model_name", sa.String(), nullable=False),
            sa.Column("version", sa.String(), nullable=False),
            sa.Column("parent_version", sa.String(), nullable=True),
            sa.Column("condition", sa.String(), nullable=False),
            sa.Column("training_round", sa.Integer(), nullable=False),
            sa.Column("participating_hospitals", sa.JSON(), nullable=False),
            sa.Column("training_metadata", sa.JSON(), nullable=False),
            sa.Column("metrics", sa.JSON(), nullable=False),
            sa.Column("validation_status", sa.String(), nullable=False),
            sa.Column("validation_report", sa.JSON(), nullable=True),
            sa.Column("deployment_status", sa.String(), nullable=False),
            sa.Column("replaces_id", sa.String(), nullable=True),
            sa.Column("artifact_hash", sa.String(), nullable=False),
            sa.Column("parameters", sa.JSON(), nullable=True),
            sa.Column("input_spec", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("approved_by", sa.String(), nullable=True),
        )
        for col in ("model_name", "condition", "training_round", "deployment_status", "created_at"):
            op.create_index(f"ix_model_versions_{col}", "model_versions", [col])


def downgrade() -> None:
    op.drop_table("model_versions")
    op.drop_table("validation_flags")
    op.drop_table("training_rounds")

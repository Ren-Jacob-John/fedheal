"""P1: scan metadata linked to cases

Revision ID: 0004_scans
Revises: 0003_cases_history_review_doctors
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_scans"
down_revision = "0003_cases_history_review_doctors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scans",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("case_id", sa.String(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("hospital_id", sa.String(), sa.ForeignKey("hospitals.id"), nullable=False),
        sa.Column("scan_type", sa.String(), nullable=False),
        sa.Column("file_reference", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("uploaded_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    for col in ("case_id", "hospital_id", "created_at"):
        op.create_index(f"ix_scans_{col}", "scans", [col])


def downgrade() -> None:
    op.drop_table("scans")

"""baseline: hospitals, users, vitals_records as of week 9

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-14

This is the schema as it existed BEFORE Sprint A — i.e. exactly what
`Base.metadata.create_all()` has been producing up to now. It contains no
new work on purpose.

Why a no-op-for-existing-databases baseline exists at all: every database
currently out there (local SQLite files, the Supabase project) was built by
create_all and has no alembic_version table. Alembic has no way to know
those tables already exist. So:

  * EXISTING database (tables already present, built by create_all):
        alembic stamp 0001_baseline
        alembic upgrade head
    The stamp records "you are already at the baseline" without running
    this file, then 0002 applies the actual new columns.

  * FRESH database (nothing there yet):
        alembic upgrade head
    This file creates the tables, then 0002 adds the new columns.

Getting this backwards on a database with data is the failure mode worth
being careful about — `upgrade` (not `stamp`) against an existing database
will fail on "table already exists", which is noisy but harmless. The
dangerous direction is stamping a database that DOESN'T have the tables,
which leaves Alembic believing they exist. Check before you stamp:
`sqlite3 fedmed_auth.db ".tables"` or `\\dt` in psql.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hospitals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        # native_enum=False stores the role as a VARCHAR with a CHECK
        # constraint rather than a Postgres ENUM type. Postgres ENUMs need
        # ALTER TYPE to add a value, which is a migration hazard the moment
        # someone adds a fourth role — and SQLite has no ENUM at all, so
        # this also keeps both backends on the same representation.
        sa.Column(
            "role",
            sa.Enum("SUPER_ADMIN", "HOSPITAL_ADMIN", "CLINICIAN",
                    name="role", native_enum=False),
            nullable=False,
        ),
        # Nullable: SUPER_ADMIN isn't scoped to a hospital.
        sa.Column("hospital_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "vitals_records",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("hospital_id", sa.String(), nullable=False),
        sa.Column("patient_ref", sa.String(), nullable=False),
        sa.Column("age_years", sa.Float(), nullable=False),
        sa.Column("height_cm", sa.Float(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("systolic_bp", sa.Float(), nullable=True),
        sa.Column("diastolic_bp", sa.Float(), nullable=True),
        sa.Column("heart_rate_bpm", sa.Float(), nullable=True),
        sa.Column("medication_count", sa.Integer(), nullable=False),
        sa.Column("medication_mg_total", sa.Float(), nullable=False),
        sa.Column("label", sa.Integer(), nullable=True),
        sa.Column("validation_status", sa.String(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_vitals_records_hospital_id"), "vitals_records", ["hospital_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_vitals_records_hospital_id"), table_name="vitals_records")
    op.drop_table("vitals_records")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.drop_table("hospitals")

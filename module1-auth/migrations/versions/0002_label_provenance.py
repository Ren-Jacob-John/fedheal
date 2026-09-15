"""sprint A: hospitals.requires_label + vitals_records.label_source

Revision ID: 0002_label_provenance
Revises: 0001_baseline
Create Date: 2026-09-14

Adds the two columns Sprint A's label-integrity work needs, and backfills
`label_source` for rows that already exist.

The backfill is the part that matters. Adding the column with a server
default of 'missing' would mark every historical record as unlabeled —
including the ones that DO carry a real label, uploaded during week 10's
real-label work. Those rows would then be excluded from training by the
new `labeled_only=true` export default, and a hospital's usable dataset
would silently shrink the moment this migration ran. So: derive
label_source from whether `label` is actually populated.

Both columns are added NOT NULL with a server_default so the ALTER
succeeds on a table with existing rows. The server defaults are then
dropped, because the application layer sets these explicitly
(main._label_source) and a lingering database default would let a future
code path insert a row without declaring provenance — quietly defaulting
to "missing" rather than failing, which is the exact class of silence this
whole sprint item is about removing.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_label_provenance"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- hospitals.requires_label ---
    with op.batch_alter_table("hospitals") as batch_op:
        batch_op.add_column(
            sa.Column("requires_label", sa.Boolean(), nullable=False,
                      server_default=sa.false())
        )

    # Existing hospitals default to False: not requiring labels is the
    # pre-Sprint-A behaviour, and flipping a tenant to "we reject your
    # unlabeled uploads now" is a decision for that hospital to make
    # explicitly, not something a migration should do on their behalf.
    with op.batch_alter_table("hospitals") as batch_op:
        batch_op.alter_column("requires_label", server_default=None)

    # --- vitals_records.label_source ---
    with op.batch_alter_table("vitals_records") as batch_op:
        batch_op.add_column(
            sa.Column("label_source", sa.String(), nullable=False,
                      server_default="missing")
        )

    # Backfill from reality rather than trusting the default. See the
    # module docstring for why this isn't optional.
    op.execute(
        "UPDATE vitals_records SET label_source = 'hospital' WHERE label IS NOT NULL"
    )

    with op.batch_alter_table("vitals_records") as batch_op:
        batch_op.alter_column("label_source", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("vitals_records") as batch_op:
        batch_op.drop_column("label_source")
    with op.batch_alter_table("hospitals") as batch_op:
        batch_op.drop_column("requires_label")

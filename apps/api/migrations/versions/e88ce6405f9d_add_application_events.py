"""add application events

Revision ID: e88ce6405f9d
Revises: 04669cf43066
Create Date: 2026-11-11 16:01:20.087774

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e88ce6405f9d"
down_revision: str | Sequence[str] | None = "04669cf43066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The application_stage type was created with the applications table; reuse it here.
stage = postgresql.ENUM(name="application_stage", create_type=False)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "application_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("from_stage", stage, nullable=True),
        sa.Column("to_stage", stage, nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_events_application_id_occurred_at",
        "application_events",
        ["application_id", "occurred_at"],
        unique=False,
    )
    # Give applications that existed before this migration their first history event.
    op.execute(
        "INSERT INTO application_events (id, application_id, from_stage, to_stage, occurred_at) "
        "SELECT gen_random_uuid(), id, NULL, stage, created_at FROM applications"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_application_events_application_id_occurred_at", table_name="application_events"
    )
    op.drop_table("application_events")

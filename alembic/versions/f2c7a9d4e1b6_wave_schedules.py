"""cronograma de habilitación de las olas (HU-37)

Revision ID: f2c7a9d4e1b6
Revises: e3b9d4a7c2f1
Create Date: 2026-11-07 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f2c7a9d4e1b6"
down_revision: str | Sequence[str] | None = "e3b9d4a7c2f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "wave_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("segmentation_id", sa.Integer(), nullable=False),
        sa.Column("opening_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closing_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "confirmed", "invalidated", name="wave_schedule_status"),
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_by_id", sa.Integer(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["club_id"], ["clubes.id"]),
        sa.ForeignKeyConstraint(
            ["event_id"], ["eventos_visibles.id_interno"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["segmentation_id"], ["wave_segmentations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["generated_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["confirmed_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_wave_schedules_event_id"),
    )
    op.create_index(
        op.f("ix_wave_schedules_club_id"),
        "wave_schedules",
        ["club_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_wave_schedules_club_id"), table_name="wave_schedules")
    op.drop_table("wave_schedules")
    op.execute("DROP TYPE wave_schedule_status")

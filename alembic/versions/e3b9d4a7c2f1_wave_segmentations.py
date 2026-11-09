"""segmentación de socios en olas (HU-36)

Revision ID: e3b9d4a7c2f1
Revises: a8f3c2d1e9b4
Create Date: 2026-11-07 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e3b9d4a7c2f1"
down_revision: str | Sequence[str] | None = "a8f3c2d1e9b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "wave_segmentations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("ranking_id", sa.Integer(), nullable=False),
        sa.Column("ranked_total", sa.Integer(), nullable=False),
        sa.Column("percentile_step", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_by_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["club_id"], ["clubes.id"]),
        sa.ForeignKeyConstraint(
            ["event_id"], ["eventos_visibles.id_interno"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["ranking_id"], ["rankings.id"]),
        sa.ForeignKeyConstraint(["generated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_wave_segmentations_event_id"),
    )
    op.create_index(
        op.f("ix_wave_segmentations_club_id"),
        "wave_segmentations",
        ["club_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_wave_segmentations_club_id"), table_name="wave_segmentations"
    )
    op.drop_table("wave_segmentations")

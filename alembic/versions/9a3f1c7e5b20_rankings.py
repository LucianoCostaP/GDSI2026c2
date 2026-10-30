"""rankings y ranking_entries (HU-25)

Revision ID: 9a3f1c7e5b20
Revises: f1a6c3d8b2e9
Create Date: 2026-10-29 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9a3f1c7e5b20"
down_revision: str | Sequence[str] | None = "f1a6c3d8b2e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "rankings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rules_version_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("running", "completed", "failed", name="ranking_state"),
            nullable=False,
        ),
        sa.Column("calculation_date", sa.Date(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("population_size", sa.Integer(), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["club_id"], ["clubes.id"]),
        sa.ForeignKeyConstraint(["rules_version_id"], ["rules_versions.id"]),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_rankings_club_id"), "rankings", ["club_id"], unique=False)
    op.create_table(
        "ranking_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ranking_id", sa.Integer(), nullable=False),
        sa.Column("socio_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("attendance_frequency", sa.Numeric(6, 2), nullable=False),
        sa.Column("attendance_distance", sa.Numeric(6, 2), nullable=False),
        sa.Column("institutional", sa.Numeric(6, 2), nullable=False),
        sa.Column("seniority_age", sa.Numeric(6, 2), nullable=False),
        sa.Column("new_member_bonus", sa.Numeric(6, 2), nullable=False),
        sa.Column("cap_adjustment", sa.Numeric(6, 2), nullable=False),
        sa.Column("total", sa.Numeric(6, 2), nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["ranking_id"], ["rankings.id"]),
        sa.ForeignKeyConstraint(["socio_id"], ["socios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ranking_id", "position", name="uq_ranking_entries_ranking_position"
        ),
        sa.UniqueConstraint(
            "ranking_id", "socio_id", name="uq_ranking_entries_ranking_socio"
        ),
    )
    op.create_index(
        op.f("ix_ranking_entries_ranking_id"),
        "ranking_entries",
        ["ranking_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_ranking_entries_ranking_id"), table_name="ranking_entries")
    op.drop_table("ranking_entries")
    op.drop_index(op.f("ix_rankings_club_id"), table_name="rankings")
    op.drop_table("rankings")
    op.execute("DROP TYPE ranking_state")
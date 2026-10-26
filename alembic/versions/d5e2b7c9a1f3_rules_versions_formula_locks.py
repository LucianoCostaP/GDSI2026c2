"""rules_versions y formula_locks (HU-27)

Revision ID: d5e2b7c9a1f3
Revises: c3d9a1f4b2e7
Create Date: 2026-10-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d5e2b7c9a1f3"
down_revision: str | Sequence[str] | None = "c3d9a1f4b2e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "rules_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("formula_id", sa.String(length=64), nullable=False),
        sa.Column("formula_version", sa.Integer(), nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "state",
            sa.Enum("in_force", "superseded", name="rules_version_state"),
            nullable=False,
        ),
        sa.Column("published_by_id", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_version_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["club_id"], ["clubes.id"]),
        sa.ForeignKeyConstraint(["published_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["previous_version_id"], ["rules_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("club_id", "number", name="uq_rules_versions_club_number"),
    )
    op.create_index(
        op.f("ix_rules_versions_club_id"), "rules_versions", ["club_id"], unique=False
    )
    op.create_index(
        "uq_rules_versions_in_force",
        "rules_versions",
        ["club_id"],
        unique=True,
        postgresql_where=sa.text("state = 'in_force'"),
    )
    op.create_table(
        "formula_locks",
        sa.Column("club_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "state",
            sa.Enum("unlocked", "locked", name="formula_lock_state"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_by_id", sa.Integer(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["club_id"], ["clubes.id"]),
        sa.ForeignKeyConstraint(["changed_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("club_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("formula_locks")
    op.drop_index("uq_rules_versions_in_force", table_name="rules_versions")
    op.drop_index(op.f("ix_rules_versions_club_id"), table_name="rules_versions")
    op.drop_table("rules_versions")
    op.execute("DROP TYPE formula_lock_state")
    op.execute("DROP TYPE rules_version_state")

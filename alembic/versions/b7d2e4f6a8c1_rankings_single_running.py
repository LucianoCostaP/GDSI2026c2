"""una sola corrida de ranking en curso por club (HU-25, Ciclo 5)

Revision ID: b7d2e4f6a8c1
Revises: 9a3f1c7e5b20
Create Date: 2026-10-31 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7d2e4f6a8c1"
down_revision: str | Sequence[str] | None = "9a3f1c7e5b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "uq_rankings_running",
        "rankings",
        ["club_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_rankings_running",
        table_name="rankings",
        postgresql_where=sa.text("status = 'running'"),
    )
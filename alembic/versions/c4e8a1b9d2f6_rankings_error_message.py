"""detalle del error de una corrida de ranking fallida (HU-25, Ciclo 7)

Revision ID: c4e8a1b9d2f6
Revises: b7d2e4f6a8c1
Create Date: 2026-10-31 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4e8a1b9d2f6"
down_revision: str | Sequence[str] | None = "b7d2e4f6a8c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("rankings", sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("rankings", "error_message")
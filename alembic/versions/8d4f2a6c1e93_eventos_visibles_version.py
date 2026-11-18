"""eventos_visibles.version: control de concurrencia de HU-23B

Cada reprogramación o retiro sube la versión; el Admin manda la que vio en el listado y la
acción falla con `EVENT_CHANGED` si otro Admin cambió el evento en el medio (FR-011).

Revision ID: 8d4f2a6c1e93
Revises: 5b1e9c3a7d20
Create Date: 2026-11-18 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d4f2a6c1e93"
down_revision: str | Sequence[str] | None = "5b1e9c3a7d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "eventos_visibles",
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("eventos_visibles", "version")

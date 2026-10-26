"""eventos_visibles: quién publicó y si la clase o los puntos fueron por defecto

HU-22 FR-007: registrar quién publicó (Admin o sistema) y si la clase o los
puntos fueron elegidos o los valores por defecto.

Revision ID: b4c8d2e6f1a3
Revises: e7a1b2c3d4e5
Create Date: 2026-10-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4c8d2e6f1a3"
down_revision: str | Sequence[str] | None = "e7a1b2c3d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "eventos_visibles",
        sa.Column(
            "publicado_por",
            sa.String(length=10),
            server_default="admin",
            nullable=False,
        ),
    )
    op.add_column(
        "eventos_visibles",
        sa.Column(
            "es_default",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_eventos_visibles_publicado_por",
        "eventos_visibles",
        "publicado_por IN ('admin', 'system')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_eventos_visibles_publicado_por", "eventos_visibles", type_="check"
    )
    op.drop_column("eventos_visibles", "es_default")
    op.drop_column("eventos_visibles", "publicado_por")

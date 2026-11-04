"""configuración de la posición estimada del simulador por club (HU-18, FR-010)

Revision ID: a8f3c2d1e9b4
Revises: c4e8a1b9d2f6
Create Date: 2026-11-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a8f3c2d1e9b4"
down_revision: str | Sequence[str] | None = "c4e8a1b9d2f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Proyección encendida por defecto (decisión del equipo: no toca el ranking real); el
    # resto, los valores de cross-cutting §8. El Admin los cambia desde
    # `/admin/simulator/settings`.
    op.add_column(
        "clubes",
        sa.Column(
            "position_projection_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "clubes",
        sa.Column(
            "position_range_level",
            sa.Numeric(3, 2),
            server_default=sa.text("0.80"),
            nullable=False,
        ),
    )
    op.add_column(
        "clubes",
        sa.Column(
            "position_prior_strength",
            sa.Numeric(6, 2),
            server_default=sa.text("5"),
            nullable=False,
        ),
    )
    op.add_column(
        "clubes",
        sa.Column(
            "position_min_population",
            sa.Integer(),
            server_default=sa.text("100"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("clubes", "position_min_population")
    op.drop_column("clubes", "position_prior_strength")
    op.drop_column("clubes", "position_range_level")
    op.drop_column("clubes", "position_projection_enabled")

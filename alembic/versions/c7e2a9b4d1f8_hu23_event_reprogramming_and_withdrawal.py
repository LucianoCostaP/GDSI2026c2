"""hu23 event reprogramming withdrawal restoration and notifications

Revision ID: c7e2a9b4d1f8
Revises: 14299b328d88
Create Date: 2026-11-14 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e2a9b4d1f8"
down_revision: str | Sequence[str] | None = "14299b328d88"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Agregar columnas a eventos_visibles para HU-23
    op.add_column(
        "eventos_visibles",
        sa.Column(
            "estado", sa.String(length=20), server_default="publicado", nullable=False
        ),
    )
    op.add_column(
        "eventos_visibles",
        sa.Column(
            "cancelado_por_el_club",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "eventos_visibles",
        sa.Column("fin_ajuste_clase_puntos", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "eventos_visibles",
        sa.Column("retirado_en", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "eventos_visibles",
        sa.Column(
            "retirado_por_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True
        ),
    )
    op.add_column(
        "eventos_visibles",
        sa.Column("motivo_retiro", sa.Text(), nullable=True),
    )
    op.add_column(
        "eventos_visibles",
        sa.Column("restaurado_en", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "eventos_visibles",
        sa.Column(
            "restaurado_por_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True
        ),
    )

    # 2. Agregar columna a eventos_pendientes_verificacion
    op.add_column(
        "eventos_pendientes_verificacion",
        sa.Column(
            "cancelado_por_el_club",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )

    # 3. Agregar columnas a eventos_cambios_pendientes
    op.add_column(
        "eventos_cambios_pendientes",
        sa.Column("tipo", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "eventos_cambios_pendientes",
        sa.Column("valores_previos", JSONB(), nullable=True),
    )
    op.add_column(
        "eventos_cambios_pendientes",
        sa.Column(
            "revisado_por_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True
        ),
    )
    op.add_column(
        "eventos_cambios_pendientes",
        sa.Column("revisado_en", sa.DateTime(timezone=True), nullable=True),
    )

    # 4. Crear tabla de notificaciones para eventos (cimientos para el equipo de notificaciones)
    op.execute("""
        CREATE TABLE IF NOT EXISTS notificaciones_eventos (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            club_id UUID NOT NULL REFERENCES clubes(id) ON DELETE CASCADE,
            event_id VARCHAR(64) NOT NULL,
            tipo_notificacion VARCHAR(50) NOT NULL,
            titulo VARCHAR(200) NOT NULL,
            mensaje TEXT NOT NULL,
            datos_evento JSONB,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            procesado BOOLEAN NOT NULL DEFAULT FALSE,
            procesado_en TIMESTAMPTZ
        );

        CREATE INDEX IF NOT EXISTS idx_notif_club_procesado ON notificaciones_eventos (club_id, procesado);
        CREATE INDEX IF NOT EXISTS idx_notif_evento ON notificaciones_eventos (event_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notificaciones_eventos CASCADE;")

    op.drop_column("eventos_cambios_pendientes", "revisado_en")
    op.drop_column("eventos_cambios_pendientes", "revisado_por_id")
    op.drop_column("eventos_cambios_pendientes", "valores_previos")
    op.drop_column("eventos_cambios_pendientes", "tipo")

    op.drop_column("eventos_pendientes_verificacion", "cancelado_por_el_club")

    op.drop_column("eventos_visibles", "restaurado_por_id")
    op.drop_column("eventos_visibles", "restaurado_en")
    op.drop_column("eventos_visibles", "motivo_retiro")
    op.drop_column("eventos_visibles", "retirado_por_id")
    op.drop_column("eventos_visibles", "retirado_en")
    op.drop_column("eventos_visibles", "fin_ajuste_clase_puntos")
    op.drop_column("eventos_visibles", "cancelado_por_el_club")
    op.drop_column("eventos_visibles", "estado")

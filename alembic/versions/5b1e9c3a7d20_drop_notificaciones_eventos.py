"""drop notificaciones_eventos: HU-23 avisa por notifications (HU-19/20)

La cola propia de HU-23 nunca tuvo consumidor; la reprogramación, el retiro y la restauración
ahora generan sus notificaciones con `notify` sobre la tabla `notifications`.

Revision ID: 5b1e9c3a7d20
Revises: 03658fcda9ee
Create Date: 2026-11-17 23:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b1e9c3a7d20"
down_revision: str | Sequence[str] | None = "03658fcda9ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notificaciones_eventos CASCADE;")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notificaciones_eventos (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            club_id UUID NOT NULL REFERENCES clubes(id) ON DELETE CASCADE,
            event_id VARCHAR(64) NOT NULL,
            tipo_notificacion VARCHAR(50) NOT NULL,
            titulo VARCHAR(200) NOT NULL,
            mensaje TEXT NOT NULL,
            datos_evento JSONB,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            procesado BOOLEAN NOT NULL DEFAULT false,
            procesado_en TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS idx_notif_club_procesado
            ON notificaciones_eventos (club_id, procesado);
        CREATE INDEX IF NOT EXISTS idx_notif_evento ON notificaciones_eventos (event_id);
        """
    )

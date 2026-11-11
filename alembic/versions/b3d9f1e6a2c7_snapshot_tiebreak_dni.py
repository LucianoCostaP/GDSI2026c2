"""documento del socio en la instantánea de cada entrada del ranking (regla 4 y 5)

Las entradas calculadas antes de este cambio no traen el grupo `tiebreak` con el documento
que usa el desempate. Se completa desde `socios`, que es el mismo dato que leyó la corrida
(el documento no cambia). Idempotente: solo toca las entradas que todavía no lo tienen, así
que es segura en cada deploy.

Revision ID: b3d9f1e6a2c7
Revises: a8f3c2d1e9b4
Create Date: 2026-11-07 20:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b3d9f1e6a2c7"
down_revision: str | Sequence[str] | None = "a8f3c2d1e9b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega `tiebreak.dni` a las instantáneas que no lo tienen."""
    op.execute(
        """
        UPDATE ranking_entries AS e
        SET inputs = e.inputs || jsonb_build_object(
            'tiebreak', jsonb_build_object('dni', s.dni)
        )
        FROM socios AS s
        WHERE s.id = e.socio_id
          AND NOT (e.inputs ? 'tiebreak')
        """
    )


def downgrade() -> None:
    """Saca el grupo `tiebreak` de las instantáneas."""
    op.execute("UPDATE ranking_entries SET inputs = inputs - 'tiebreak'")

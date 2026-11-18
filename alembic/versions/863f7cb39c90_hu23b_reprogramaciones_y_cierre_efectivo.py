"""HU-23B: reprogramaciones del Admin y cierre efectivo del cronograma

`event_reprogrammings` guarda cada reprogramación (su id va en la clave de las
notificaciones). `wave_schedules` gana el cierre efectivo y la última ola separada: las
horas de las olas se siguen derivando del cierre generado, así que un ajuste nunca corre
una ola que no se fusionó. Las columnas nuevas son nulas: los cronogramas existentes
quedan como estaban.

Revision ID: 863f7cb39c90
Revises: 8d4f2a6c1e93
Create Date: 2026-11-18 01:53:08.704264

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "863f7cb39c90"
down_revision: str | Sequence[str] | None = "8d4f2a6c1e93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_reprogrammings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("club_id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("previous_fecha_hora", sa.DateTime(timezone=True), nullable=False),
        sa.Column("new_fecha_hora", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schedule_effect", sa.String(length=32), nullable=False),
        sa.Column("reprogrammed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reprogrammed_by_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["club_id"],
            ["clubes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["eventos_visibles.id_interno"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reprogrammed_by_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_event_reprogrammings_club_id"),
        "event_reprogrammings",
        ["club_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_event_reprogrammings_event_id"),
        "event_reprogrammings",
        ["event_id"],
        unique=False,
    )
    op.add_column(
        "wave_schedules",
        sa.Column("effective_closing_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "wave_schedules", sa.Column("merged_into_order", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("wave_schedules", "merged_into_order")
    op.drop_column("wave_schedules", "effective_closing_at")
    op.drop_index(
        op.f("ix_event_reprogrammings_event_id"), table_name="event_reprogrammings"
    )
    op.drop_index(
        op.f("ix_event_reprogrammings_club_id"), table_name="event_reprogrammings"
    )
    op.drop_table("event_reprogrammings")

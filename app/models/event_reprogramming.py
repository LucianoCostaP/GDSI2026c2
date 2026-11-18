"""Reprogramación de un evento publicado por el Admin (HU-23B US2, Key Entities).

Una fila por reprogramación aplicada: la fecha anterior y la nueva, y el efecto sobre el
cronograma de olas. Su id forma parte de la clave de las notificaciones, así que repetir el
mismo pedido nunca avisa dos veces.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .auth import utcnow


class EventReprogramming(Base):
    __tablename__ = "event_reprogrammings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id"), index=True
    )
    event_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("eventos_visibles.id_interno", ondelete="CASCADE"),
        index=True,
    )
    previous_fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    new_fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # `no_schedule`, `none`, `closing_adjusted`, `waves_merged` o `invalidated`
    # (`scoring.wave_schedule.ScheduleEffect`).
    schedule_effect: Mapped[str] = mapped_column(String(32))
    reprogrammed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    reprogrammed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

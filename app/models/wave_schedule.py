"""Cronograma de habilitación de las olas de un Partido (HU-37).

Se guardan solo la apertura y el cierre general: la hora de inicio de cada ola se deriva
con `scoring/wave_schedule.py`, igual que las olas se derivan de la segmentación (HU-36).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .auth import pg_enum, utcnow


class WaveScheduleStatus(enum.StrEnum):
    # Generado, a la espera de que el Admin lo confirme. Los socios no lo ven.
    DRAFT = "draft"
    # Confirmado por el Admin: es el que ven los socios (HU-39).
    CONFIRMED = "confirmed"
    # Las olas se regeneraron (HU-36): ya no vale y hay que generar otro.
    INVALIDATED = "invalidated"


class WaveSchedule(Base):
    __tablename__ = "wave_schedules"
    # Uno solo por evento: regenerar actualiza esta fila.
    __table_args__ = (UniqueConstraint("event_id", name="uq_wave_schedules_event_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id"), index=True
    )
    event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("eventos_visibles.id_interno", ondelete="CASCADE")
    )
    segmentation_id: Mapped[int] = mapped_column(
        ForeignKey("wave_segmentations.id", ondelete="CASCADE")
    )
    # Apertura de la primera ola y cierre general, en UTC.
    opening_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closing_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[WaveScheduleStatus] = mapped_column(
        pg_enum(WaveScheduleStatus, "wave_schedule_status"),
        default=WaveScheduleStatus.DRAFT,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    generated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

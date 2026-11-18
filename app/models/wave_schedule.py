"""Cronograma de habilitación de las olas de un Partido (HU-37).

Se guardan solo la apertura y el cierre general: la hora de inicio de cada ola se deriva
con `scoring/wave_schedule.py`, igual que las olas se derivan de la segmentación (HU-36).
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .auth import pg_enum, utcnow


class WaveScheduleStatus(enum.StrEnum):
    # Generado, a la espera de que el Admin lo confirme. Los socios no lo ven.
    DRAFT = "draft"
    # Confirmado por el Admin: es el que ven los socios (HU-39).
    CONFIRMED = "confirmed"
    # Ya no vale y hay que generar otro: se regeneraron las olas (HU-36) o una
    # reprogramación dejó todas las olas después del inicio (HU-23B). Ver `invalidation_reason`.
    INVALIDATED = "invalidated"


class WaveScheduleInvalidation(enum.StrEnum):
    """Por qué se invalidó un cronograma, para decírselo al Admin (HU-37, HU-23B US3)."""

    # Se regeneraron las olas del Partido (HU-36 FR-007).
    WAVES_REGENERATED = "waves_regenerated"
    # Una reprogramación dejó todas las olas afectadas o solapó un borrador (HU-23B US3,
    # escenarios 6 y 7).
    EVENT_RESCHEDULED = "event_rescheduled"


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
    # Apertura de la primera ola y cierre general con el que se generó, en UTC. Las horas de
    # inicio de las olas se derivan siempre de estos dos, aunque una reprogramación mueva el
    # cierre (HU-23B): así un ajuste nunca corre una ola que no se fusionó.
    opening_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closing_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Cierre general después de los ajustes de HU-23B; `None` mientras es el generado.
    effective_closing_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Última ola separada después de una fusión (HU-23B US3): las olas siguientes toman su
    # hora de inicio. `None` si no se fusionó ninguna. Regenerar limpia los dos campos.
    merged_into_order: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[WaveScheduleStatus] = mapped_column(
        pg_enum(WaveScheduleStatus, "wave_schedule_status"),
        default=WaveScheduleStatus.DRAFT,
    )
    # Solo con `status = invalidated` (un `WaveScheduleInvalidation`); `None` en los
    # invalidados antes de que existiera. Regenerar lo limpia.
    invalidation_reason: Mapped[str | None] = mapped_column(String(32))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    generated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    @property
    def effective_closing(self) -> datetime:
        """El cierre general vigente: el ajustado por una reprogramación, o el generado."""
        return self.effective_closing_at or self.closing_at

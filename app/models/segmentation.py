"""Segmentación de socios en olas de un Partido (HU-36).

No se guarda nada por socio: la ola de cada uno sale de su posición en el ranking usado.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .auth import utcnow


class WaveSegmentation(Base):
    __tablename__ = "wave_segmentations"
    # Una sola por evento: regenerar actualiza esta fila.
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_wave_segmentations_event_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id"), index=True
    )
    event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("eventos_visibles.id_interno", ondelete="CASCADE")
    )
    ranking_id: Mapped[int] = mapped_column(ForeignKey("rankings.id"))
    ranked_total: Mapped[int] = mapped_column(Integer)
    # Copia del setting al generar: cambiarlo después no altera esta segmentación.
    percentile_step: Mapped[int] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    generated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

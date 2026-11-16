"""Cimientos para el sistema de notificaciones de eventos a los socios (HU-23 y feature de notificaciones).

Este módulo define la persistencia y entidades de las notificaciones originadas
por cambios en el ciclo de vida de los eventos (reprogramación, retiro, restauración).
El equipo a cargo del sistema de notificaciones por app o email puede consumir
estas entidades y colas directamente sin acoplarse a la lógica interna de eventos.
"""

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class TipoNotificacionEvento(enum.StrEnum):
    EVENTO_REPROGRAMADO = "evento_reprogramado"
    EVENTO_RETIRADO = "evento_retirado"
    EVENTO_RESTAURADO = "evento_restaurado"


class EventNotificationDB(Base):
    """Cola / registro de notificaciones de eventos pendientes de despacho a socios."""

    __tablename__ = "notificaciones_eventos"
    __table_args__ = (
        Index("idx_notif_club_procesado", "club_id", "procesado"),
        Index("idx_notif_evento", "event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tipo_notificacion: Mapped[str] = mapped_column(String(50), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    datos_evento: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    procesado: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    procesado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

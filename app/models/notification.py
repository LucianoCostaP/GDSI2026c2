"""Notificaciones de los Socios (HU-20 crea la tabla; HU-19 las genera y suma el correo).

Cada notificación guarda su texto congelado al generarse y una referencia (`event_id` o
`ranking_id`), nunca una URL: el front arma el destino (notificaciones §3). El par
(cuenta, `occurrence_key`) es único, así que generar dos veces la misma ocurrencia no duplica
(notificaciones §4).
"""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .auth import pg_enum, utcnow


class NotificationState(enum.StrEnum):
    UNREAD = "unread"
    READ = "read"


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "occurrence_key", name="uq_notifications_user_occurrence"
        ),
        # La bandeja ordena por fecha y el contador cuenta por estado, siempre de una cuenta.
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_user_state", "user_id", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id")
    )
    # La cuenta del Socio (`users.id`): la bandeja es de la cuenta de la sesión.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Clave del catálogo (notificaciones §2). Texto y no enum de Postgres: sumar un tipo es
    # una versión del producto y no tiene que exigir una migración.
    type: Mapped[str] = mapped_column(String(40))
    # `{"event_id": "<id_interno>"}` o `{"ranking_id": 42}`.
    reference: Mapped[dict[str, Any]] = mapped_column(JSONB)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    state: Mapped[NotificationState] = mapped_column(
        pg_enum(NotificationState, "notification_state"),
        default=NotificationState.UNREAD,
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurrence_key: Mapped[str] = mapped_column(String(200))

"""Respuestas de la bandeja de notificaciones del Socio (HU-20).

Ver `docs/contrato-api-notificaciones.md`, sección 3.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    id: int
    type: str = Field(description="Clave del catálogo (notificaciones §2)")
    title: str
    message: str = Field(description="Texto congelado al generar la notificación")
    created_at: datetime = Field(description="Fecha y hora de generación, en UTC")
    state: Literal["unread", "read"]
    read_at: datetime | None = Field(
        description="Primera vez que se leyó, en UTC; `null` si no se leyó"
    )
    reference: dict[str, Any] = Field(
        description='`{"event_id": "<id_interno>"}` o `{"ranking_id": 42}`'
    )


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread_count: int = Field(description="Igual al de `/unread-count`")
    limit: int
    offset: int


class ReadAllOut(BaseModel):
    marked: int = Field(
        description="Cuántas estaban sin leer y se marcaron; puede ser 0"
    )
    unread_count: int = Field(description="Siempre 0 después de marcar todas")


class UnreadCountOut(BaseModel):
    unread_count: int = Field(
        description="Número exacto; el `99+` y el ocultarlo con 0 los resuelve el front"
    )

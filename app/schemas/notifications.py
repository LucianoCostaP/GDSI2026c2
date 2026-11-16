"""Respuestas de la bandeja de notificaciones del Socio (HU-20).

Ver `docs/contrato-api-notificaciones.md`, sección 3.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NotificationOut(BaseModel):
    id: int
    type: str = Field(description="Clave del catálogo (notificaciones §2)")
    title: str
    message: str = Field(description="Texto congelado al generar la notificación")
    created_at: datetime = Field(description="Fecha y hora de generación, en UTC")
    reference: dict[str, Any] = Field(
        description='`{"event_id": "<id_interno>"}` o `{"ranking_id": 42}`'
    )


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int

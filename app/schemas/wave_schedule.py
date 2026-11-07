"""Pedidos y respuestas de la API del cronograma de oleadas (HU-37)."""

from datetime import datetime

from pydantic import BaseModel

from ..models import WaveScheduleStatus
from .segmentation import SegmentationEventOut


class GenerateScheduleIn(BaseModel):
    # Apertura de la primera ola y cierre general, en ISO-8601 con zona horaria.
    opening_at: datetime
    closing_at: datetime
    # Obligatorio en `true` para reemplazar un cronograma vigente (escenario 6).
    confirmed: bool = False


class WaveScheduleOut(BaseModel):
    event: SegmentationEventOut
    status: WaveScheduleStatus
    opening_at: datetime
    closing_at: datetime
    generated_at: datetime
    generated_by: str

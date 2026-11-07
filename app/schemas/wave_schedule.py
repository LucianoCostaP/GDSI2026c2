"""Pedidos y respuestas de la API del cronograma de oleadas (HU-37)."""

from datetime import UTC, datetime

from pydantic import BaseModel, field_validator

from ..core.date_utils import BUENOS_AIRES_TZ
from ..models import WaveScheduleStatus
from .segmentation import SegmentationEventOut, WaveOut


class GenerateScheduleIn(BaseModel):
    # Apertura de la primera ola y cierre general, en ISO-8601. Sin zona horaria se leen
    # en hora de Buenos Aires (cross-cutting sección 1).
    opening_at: datetime
    closing_at: datetime
    # Obligatorio en `true` para reemplazar un cronograma vigente (escenario 6).
    confirmed: bool = False

    @field_validator("opening_at", "closing_at")
    @classmethod
    def _naive_is_buenos_aires(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=BUENOS_AIRES_TZ)
        return value.astimezone(UTC)


class ScheduledWaveOut(WaveOut):
    # Desde acá el acceso queda abierto para esta ola (y las anteriores) hasta el cierre.
    starts_at: datetime


class WaveScheduleOut(BaseModel):
    event: SegmentationEventOut
    status: WaveScheduleStatus
    opening_at: datetime
    closing_at: datetime
    # Tiempo entre la apertura de dos olas seguidas: (cierre − apertura) / N.
    step_seconds: int
    # Mínimo vigente entre oleadas (setting), para mostrarlo al Admin.
    min_step_minutes: int
    generated_at: datetime
    generated_by: str
    # Solo con `status = confirmed`: desde ahí lo ven los socios.
    confirmed_at: datetime | None
    confirmed_by: str | None
    waves: list[ScheduledWaveOut]

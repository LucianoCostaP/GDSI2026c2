"""Pedidos y respuestas de la API del cronograma de oleadas (HU-37)."""

from datetime import UTC, datetime

from pydantic import BaseModel, field_validator

from ..core.date_utils import BUENOS_AIRES_TZ
from ..models import WaveScheduleInvalidation, WaveScheduleStatus
from ..scoring.wave_schedule import WaveState
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
    # Con el reloj del servidor; `null` mientras el cronograma no está confirmado.
    state: WaveState | None


class WaveScheduleOut(BaseModel):
    event: SegmentationEventOut
    status: WaveScheduleStatus
    opening_at: datetime
    # Cierre general vigente: el generado, o el ajustado por una reprogramación (HU-23B).
    closing_at: datetime
    # El cierre con el que se generó: de él (y de la apertura) salen las horas de las olas.
    generated_closing_at: datetime
    # Última ola separada tras una fusión (HU-23B US3): las olas siguientes abren con ella,
    # "Ola k (incluye las olas k+1 a N)". `null` si no hubo fusión.
    merged_into_order: int | None = None
    # Solo con `status = invalidated`: `waves_regenerated` (HU-36) o `event_rescheduled`
    # (HU-23B US3); `None` si se invalidó antes de guardarse el motivo.
    invalidation_reason: WaveScheduleInvalidation | None = None
    # Tiempo entre la apertura de dos olas seguidas: (cierre generado − apertura) / N.
    step_seconds: int
    # Mínimo vigente entre oleadas (setting), para mostrarlo al Admin.
    min_step_minutes: int
    # La primera ola ya abrió: no se pueden regenerar ni el cronograma ni las olas.
    locked: bool
    generated_at: datetime
    generated_by: str
    # Solo con `status = confirmed`: desde ahí lo ven los socios.
    confirmed_at: datetime | None
    confirmed_by: str | None
    waves: list[ScheduledWaveOut]

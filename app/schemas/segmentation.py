"""Respuestas de la API de segmentación en olas (HU-36)."""

from datetime import datetime

from pydantic import BaseModel

from ..models import WaveScheduleStatus
from .ranking import PreflightWarningOut


class SegmentationEventOut(BaseModel):
    id_interno: str
    titulo: str
    fecha_hora: datetime
    lugar: str


class SegmentationRankingOut(BaseModel):
    id: int
    completed_at: datetime | None
    # Número de la versión de reglas que usó ese ranking.
    rules_version: int


class WaveOut(BaseModel):
    order: int
    percentile_from: int
    percentile_to: int
    position_from: int
    position_to: int
    socios: int


class SegmentationOut(BaseModel):
    event: SegmentationEventOut
    ranking: SegmentationRankingOut
    ranked_total: int
    percentile_step: int
    # Mínimo vigente entre las aperturas de dos oleadas (setting de HU-37), para que el
    # front lo muestre antes de que exista un cronograma.
    min_step_minutes: int
    generated_at: datetime
    generated_by: str
    waves: list[WaveOut]


class SegmentationSummaryOut(BaseModel):
    generated_at: datetime
    waves_count: int


class ScheduleSummaryOut(BaseModel):
    # Cronograma de las olas (HU-37): estado y período de reserva.
    status: WaveScheduleStatus
    opening_at: datetime
    # Cierre general vigente: el ajustado por una reprogramación (HU-23B), si la hubo.
    closing_at: datetime
    # Última ola separada tras una fusión (HU-23B US3); `null` si no hubo.
    merged_into_order: int | None = None


class SegmentableEventOut(BaseModel):
    event: SegmentationEventOut
    segmentation: SegmentationSummaryOut | None
    schedule: ScheduleSummaryOut | None


class SegmentationPreflightOut(BaseModel):
    warnings: list[PreflightWarningOut]
    # Las advertencias no bloquean: el Admin siempre puede generar las olas.
    can_continue: bool = True


class GenerateSegmentationIn(BaseModel):
    # Obligatorio en `true` para reemplazar olas ya generadas (escenario 7).
    confirmed: bool = False

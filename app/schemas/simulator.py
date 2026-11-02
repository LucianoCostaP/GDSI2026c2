"""Respuestas del simulador de puntaje por asistencia (HU-18, `docs/contrato-api-simulador.md`)."""

from datetime import date, datetime

from pydantic import BaseModel


class SimulatedEventOut(BaseModel):
    id: str
    titulo: str
    # "Partido" o "Evento institucional/amateur": nunca la clase ni el factor (FR-012).
    tipo: str
    fecha_hora: datetime
    # Puntos del evento institucional; `null` para un Partido.
    puntos: int | None


class SimulationRankingOut(BaseModel):
    completed_at: datetime | None
    calculation_date: date
    # Versión de reglas del ranking (no la vigente).
    rules_version: int


class CurrentStandingOut(BaseModel):
    score: str
    position: int
    ranked_total: int


class HypothesisOut(BaseModel):
    score: str
    # `score − current.score`, con signo y 2 decimales.
    difference: str
    # Posición estimada: `null` mientras no se estime (escenarios 10 y 12).
    position: None = None


class PositionEstimateOut(BaseModel):
    # "estimated" | "unavailable" | "not_estimated"
    status: str
    code: str | None
    reason: str | None
    message: str | None
    label: str | None = None
    range_level: str | None = None


class SimulationOut(BaseModel):
    event: SimulatedEventOut
    ranking: SimulationRankingOut
    current: CurrentStandingOut
    attend: HypothesisOut
    not_attend: HypothesisOut
    position_estimate: PositionEstimateOut

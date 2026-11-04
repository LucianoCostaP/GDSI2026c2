"""Respuestas del simulador de puntaje por asistencia (HU-18, `docs/contrato-api-simulador.md`)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ESTIMATED_POSITION_PREFIX = "puesto estimado "


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


class EstimatedPositionOut(BaseModel):
    """Puesto estimado de una hipótesis y su rango probable (escenario 10)."""

    estimate: int
    lower: int
    upper: int
    # "puesto estimado 3.150 (probable entre 3.136 y 3.164)", ya en es-AR.
    text: str

    @model_validator(mode="after")
    def _is_a_labeled_range(self) -> Self:
        """Escenario 13: un rango (aunque sea de un solo puesto), nunca un número exacto."""
        if not 1 <= self.lower <= self.estimate <= self.upper:
            raise ValueError("El puesto estimado tiene que estar dentro de su rango.")
        if not self.text.startswith(ESTIMATED_POSITION_PREFIX):
            raise ValueError("El texto tiene que decir que el puesto es estimado.")
        return self


class HypothesisOut(BaseModel):
    score: str
    # `score − current.score`, con signo y 2 decimales.
    difference: str
    # Solo si `position_estimate.status == "estimated"` (escenarios 10 y 12).
    position: EstimatedPositionOut | None = None


class PositionEstimateOut(BaseModel):
    # "estimated" | "unavailable" | "not_estimated"
    status: str
    code: str | None
    reason: str | None
    message: str | None
    label: str | None = None
    range_level: str | None = None


class RulesNoticeOut(BaseModel):
    """Las reglas vigentes del club ya no son las del ranking (escenario 8)."""

    code: str
    message: str


class DistanceOut(BaseModel):
    """Distancia al estadio de las proyecciones y la del ranking (escenario 9)."""

    # La del padrón al momento: la usan las dos proyecciones.
    used_km: str
    # La de la instantánea del ranking: la usa el puntaje actual.
    ranking_km: str
    changed: bool
    notice: str | None


class SimulationOut(BaseModel):
    event: SimulatedEventOut
    ranking: SimulationRankingOut
    # `null` salvo que las reglas vigentes difieran de las del ranking.
    rules_notice: RulesNoticeOut | None
    distance: DistanceOut
    current: CurrentStandingOut
    attend: HypothesisOut
    not_attend: HypothesisOut
    position_estimate: PositionEstimateOut

    @model_validator(mode="after")
    def _estimates_carry_the_label(self) -> Self:
        """Escenario 13 (SC-003): ninguna posición estimada sale sin la etiqueta.

        Las dos hipótesis traen posición si y solo si el estado es "estimated", y en ese caso
        vienen la etiqueta y el nivel del rango. Una respuesta que no lo cumple es un error
        del programa y no se devuelve.
        """
        positions = [self.attend.position, self.not_attend.position]
        estimate = self.position_estimate
        if estimate.status == "estimated":
            if any(position is None for position in positions):
                raise ValueError(
                    "Una estimación trae la posición de las dos hipótesis."
                )
            if not estimate.label or estimate.range_level is None:
                raise ValueError("Una posición estimada siempre lleva la etiqueta.")
        elif any(position is not None for position in positions):
            raise ValueError("Sin estimación no se devuelve ninguna posición estimada.")
        return self


class SimulatorStatusOut(BaseModel):
    """Si el socio puede simular (escenario 2): siempre 200."""

    # "available" | "unavailable"
    status: str
    # "NOT_IN_RANKING" cuando no puede simular.
    reason: str | None
    message: str | None
    ranking: SimulationRankingOut | None


class SimulatorSettingsOut(BaseModel):
    """Configuración del simulador del club (FR-010); los decimales viajan como texto."""

    position_projection_enabled: bool
    position_range_level: str
    position_prior_strength: str
    position_min_population: int


class SimulatorSettingsUpdate(BaseModel):
    """Cambios del Admin: solo los campos que llegan se modifican."""

    model_config = ConfigDict(extra="forbid")

    position_projection_enabled: bool | None = None
    # Nivel del rango probable: estrictamente entre 0 y 1, con 2 decimales.
    position_range_level: Decimal | None = Field(
        default=None, gt=0, lt=1, max_digits=3, decimal_places=2
    )
    # Peso `k` de la tasa del club; con 0, un socio sin historial dividiría por cero.
    position_prior_strength: Decimal | None = Field(
        default=None, gt=0, max_digits=6, decimal_places=2
    )
    position_min_population: int | None = Field(default=None, ge=1)

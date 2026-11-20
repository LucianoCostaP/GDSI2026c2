"""Respuestas de la API del cálculo del ranking (HU-25 y HU-16)."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from ..models import RankingState


class RankingRunOut(BaseModel):
    id: int
    status: RankingState
    # Número de la versión de reglas que usó la corrida.
    rules_version: int
    calculation_date: date
    calculated_at: datetime
    # Desde cuándo rige el ranking; `null` mientras la corrida está en curso.
    completed_at: datetime | None
    population_size: int
    # Mensaje para el Admin cuando la corrida falló; `null` en cualquier otro estado.
    error: str | None = None


class PreflightWarningOut(BaseModel):
    # `ROSTER_STALE`, `ATTENDANCE_STALE` o `LOADS_AFTER_LAST_RANKING`.
    code: str
    message: str
    # Fecha del dato que motiva la advertencia; `null` si el club nunca cargó ese dato.
    data_as_of: datetime | None


class RankingPreflightOut(BaseModel):
    warnings: list[PreflightWarningOut]
    # Las advertencias no bloquean: el Admin siempre puede continuar con el cálculo.
    can_continue: bool = True


class ScoreComponentOut(BaseModel):
    """Componente individual del desglose de puntaje (HU-16)."""

    key: str
    name: str
    points: str
    supporting_figures: dict[str, Any] = {}
    explanation: str | None = None


class ScoreBreakdownResponse(BaseModel):
    """Desglose de puntaje para el Socio (HU-16)."""

    has_ranking: bool
    message: str | None = None
    rules_version: int | None = None
    calculation_date: date | None = None
    total: str | None = None
    position: int | None = None
    components: list[ScoreComponentOut] = []


class PillarRankingRowOut(BaseModel):
    """Una fila del top de un pilar (HU-44). Sin DNI, email ni distancia."""

    position: int
    numero_socio: str
    nombre: str
    # Puntos del pilar con dos decimales, iguales a los del desglose (HU-16).
    points: str


class PillarRankingOut(BaseModel):
    # `attendance`, `institutional` o `seniority_age`.
    key: str
    name: str
    rows: list[PillarRankingRowOut]
    # Texto en lugar de la tabla cuando `rows` está vacío.
    empty_message: str | None = None


class PillarRankingSourceOut(BaseModel):
    """La corrida de donde salen las tablas: el ranking vigente."""

    id: int
    rules_version: int
    calculation_date: date
    completed_at: datetime


class PillarRankingsOut(BaseModel):
    """Rankings por pilar del ranking vigente (HU-44, `docs/contrato-api-ranking-pilares.md`)."""

    has_ranking: bool
    message: str | None = None
    # `true` mientras hay un cálculo en curso: las tablas siguen siendo las del último completado.
    updating: bool = False
    ranking: PillarRankingSourceOut | None = None
    pillars: list[PillarRankingOut] = []

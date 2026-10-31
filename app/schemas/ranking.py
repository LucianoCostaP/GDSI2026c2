"""Respuestas de la API del cálculo del ranking (HU-25)."""

from datetime import date, datetime

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
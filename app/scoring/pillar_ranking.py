"""Rankings por pilar del puntaje (HU-44). Código puro y determinístico.

Cada pilar es un término ponderado de la fórmula, armado con los componentes que HU-25 guarda
por socio (modelo de scoring, regla 3). El bonus de socio nuevo y el ajuste por tope no forman
parte de ningún pilar. El orden es el del ranking general con los puntos del pilar en lugar del
total: mayor puntaje y, a igualdad, mayor antigüedad, mayor edad y menor documento
(`ranking_order`), así que las posiciones dentro de un pilar son únicas. Solo entran los socios
con más de 0,00 puntos en el pilar: un pilar sin nadie con puntos queda sin filas.
"""

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .ranking_order import RankingCandidate, top_positions

TOP_LIMIT = 10


@dataclass(frozen=True)
class Pillar:
    key: str
    name: str
    # Componentes guardados en `ranking_entries` que suman los puntos del pilar.
    components: tuple[str, ...]


# Los tres pilares de `scoring-model` (modelo de scoring, sección 2), con los nombres del
# desglose de HU-16. Asistencia junta frecuencia y distancia: pesan juntas en el puntaje.
SCORING_MODEL_PILLARS: tuple[Pillar, ...] = (
    Pillar("attendance", "Asistencia", ("attendance_frequency", "attendance_distance")),
    Pillar("institutional", "Participación institucional", ("institutional",)),
    Pillar("seniority_age", "Antigüedad y edad", ("seniority_age",)),
)

# Pilares por fórmula del catálogo. Una fórmula que no figura acá no tiene rankings por pilar
# (modelo de scoring, regla 9: cada fórmula define sus componentes).
PILLARS_BY_FORMULA: Mapping[str, tuple[Pillar, ...]] = {
    "scoring-model": SCORING_MODEL_PILLARS,
}


@dataclass(frozen=True)
class PillarSource:
    """Lo que hace falta de una entrada del ranking para ubicarla en cada pilar."""

    socio_id: uuid.UUID
    components: Mapping[str, Decimal]
    seniority_start: date
    birth_date: date
    dni: str


@dataclass(frozen=True)
class PillarRow:
    position: int
    socio_id: uuid.UUID
    points: Decimal


@dataclass(frozen=True)
class PillarTop:
    pillar: Pillar
    rows: list[PillarRow]


def pillar_points(pillar: Pillar, components: Mapping[str, Decimal]) -> Decimal:
    """Puntos del socio en el pilar: la suma de sus componentes guardados (dos decimales)."""
    return sum((components[name] for name in pillar.components), Decimal(0))


def top_of_pillar(
    pillar: Pillar, sources: Iterable[PillarSource], limit: int = TOP_LIMIT
) -> PillarTop:
    """Los primeros `limit` socios con puntos en el pilar, con su posición (desde 1)."""
    candidates = (
        RankingCandidate(
            socio_id=s.socio_id,
            total=points,
            seniority_start=s.seniority_start,
            birth_date=s.birth_date,
            dni=s.dni,
        )
        for s in sources
        if (points := pillar_points(pillar, s.components)) > 0
    )
    return PillarTop(
        pillar=pillar,
        rows=[
            PillarRow(position=position, socio_id=c.socio_id, points=c.total)
            for position, c in top_positions(candidates, limit)
        ],
    )


def top_by_pillar(
    pillars: Iterable[Pillar], sources: Iterable[PillarSource], limit: int = TOP_LIMIT
) -> list[PillarTop]:
    """El top de cada pilar, en el orden en que vienen los pilares."""
    materialized = list(sources)
    return [top_of_pillar(pillar, materialized, limit) for pillar in pillars]

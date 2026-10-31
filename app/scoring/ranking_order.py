"""Orden y posiciones del ranking (modelo de scoring, regla 5; HU-25 FR-007).

Código puro y determinístico. Ordena por total (mayor primero) y desempata, en este orden, por
mayor antigüedad, mayor edad y menor número de documento:

- Antigüedad: gana quien tiene la pertenencia ininterrumpida más antigua (fecha de inicio
  exacta, no años cumplidos).
- Edad: gana quien nació antes (fecha de nacimiento exacta).
- Documento: se compara como número, no como texto ("4000000" va antes que "30000001").

El total se compara a dos decimales, tal como se guarda y se muestra. Como el documento es único
en el club, el orden es total: nunca quedan dos socios con la misma posición.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .engine import round_component


@dataclass(frozen=True)
class RankingCandidate:
    """Lo mínimo de un socio para ubicarlo en el ranking."""

    socio_id: uuid.UUID
    total: Decimal
    seniority_start: date
    birth_date: date
    dni: str


def _document_key(dni: str) -> tuple[int, int, str]:
    """Clave de orden del documento: los numéricos primero y por valor; luego el resto."""
    digits = dni.replace(".", "").replace(" ", "")
    if digits.isascii() and digits.isdigit():
        return (0, int(digits), dni)
    return (1, 0, dni)


def _sort_key(
    candidate: RankingCandidate,
) -> tuple[Decimal, date, date, tuple[int, int, str]]:
    return (
        -round_component(candidate.total),
        candidate.seniority_start,
        candidate.birth_date,
        _document_key(candidate.dni),
    )


def assign_positions(
    candidates: Iterable[RankingCandidate],
) -> list[tuple[int, RankingCandidate]]:
    """Posición (desde 1, sin saltos ni repetidos) de cada candidato, en orden de ranking."""
    ordered = sorted(candidates, key=_sort_key)
    return list(enumerate(ordered, start=1))

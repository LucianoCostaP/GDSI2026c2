"""Recálculo de un ranking guardado con otras reglas (HU-29 escenario 8; HU-30).

Código puro y determinístico, sin base de datos. Cada entrada del ranking se recalcula desde su
instantánea (`scoring_inputs_from_snapshot`) con el motor único (`engine.calculate_score`), y
el conjunto se reordena con el desempate de la regla 5 tomado de la misma instantánea
(`ranking_candidate_from_snapshot`). No hay atajos: con las reglas del ranking, el resultado es
idéntico a lo guardado (escenario 9).
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .engine import ScoringParameters, calculate_score
from .ranking_order import assign_positions
from .snapshot import ranking_candidate_from_snapshot, scoring_inputs_from_snapshot


@dataclass(frozen=True)
class StoredEntry:
    """Una entrada del ranking tal como quedó guardada (la situación "antes")."""

    socio_id: uuid.UUID
    position: int
    components: Mapping[str, Decimal]
    total: Decimal
    snapshot: Mapping[str, Any]


@dataclass(frozen=True)
class SimulatedEntry:
    """El mismo socio recalculado con los valores hipotéticos (la situación "después")."""

    socio_id: uuid.UUID
    position: int
    components: Mapping[str, Decimal]
    total: Decimal


@dataclass(frozen=True)
class Movement:
    """Cuántos socios suben, bajan o quedan en su posición (escenario 13)."""

    up: int
    down: int
    unchanged: int


def simulate_entries(
    entries: Sequence[StoredEntry], params: ScoringParameters
) -> list[SimulatedEntry]:
    """Recalcula cada entrada y les da posición. Devuelve una por entrada, en el mismo orden.

    La población es exactamente la de `entries`: ni se agregan ni se quitan socios.
    """
    scores = [
        calculate_score(scoring_inputs_from_snapshot(entry.snapshot), params)
        for entry in entries
    ]
    candidates = [
        ranking_candidate_from_snapshot(entry.socio_id, score.total, entry.snapshot)
        for entry, score in zip(entries, scores, strict=True)
    ]
    positions = {
        candidate.socio_id: position
        for position, candidate in assign_positions(candidates)
    }
    return [
        SimulatedEntry(
            socio_id=entry.socio_id,
            position=positions[entry.socio_id],
            components=score.components,
            total=score.total,
        )
        for entry, score in zip(entries, scores, strict=True)
    ]


def position_change(before: StoredEntry, after: SimulatedEntry) -> int:
    """`posición del ranking − posición simulada`: positivo sube, negativo baja."""
    return before.position - after.position


def movement(
    before: Sequence[StoredEntry], after: Sequence[SimulatedEntry]
) -> Movement:
    """Suben, bajan y sin cambio. `after` viene en el orden de `before` (`simulate_entries`)."""
    changes = [position_change(b, a) for b, a in zip(before, after, strict=True)]
    return Movement(
        up=sum(1 for c in changes if c > 0),
        down=sum(1 for c in changes if c < 0),
        unchanged=sum(1 for c in changes if c == 0),
    )


# --- Parámetros cambiados y factores (escenario 17) ----------------------------------------

PILLAR_WEIGHTS = "pillar_weights"
OTHER = "other"
# Orden fijo de los factores (escenario 17; también desempata el escenario 18).
FACTORS: tuple[str, ...] = (PILLAR_WEIGHTS, "alpha_a", "d_sat", OTHER)
_PILLAR_KEYS = frozenset({"w_a", "w_p", "w_t"})


def factor_of(key: str) -> str:
    """Factor de un parámetro: los tres pesos van juntos porque tienen que sumar 1."""
    if key in _PILLAR_KEYS:
        return PILLAR_WEIGHTS
    if key in ("alpha_a", "d_sat"):
        return key
    return OTHER


def changed_keys(
    before: Mapping[str, Decimal], after: Mapping[str, Decimal]
) -> list[str]:
    """Parámetros cuyo valor hipotético difiere del de las reglas del ranking, en el orden de
    `before`. Se comparan como `Decimal` ("0.6" y "0.60" son iguales)."""
    return [key for key, value in before.items() if after[key] != value]


def factors_changed(keys: Sequence[str]) -> list[str]:
    """Factores con al menos un parámetro cambiado, en el orden de `FACTORS`."""
    touched = {factor_of(key) for key in keys}
    return [factor for factor in FACTORS if factor in touched]

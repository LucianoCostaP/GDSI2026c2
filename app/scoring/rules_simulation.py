"""Recálculo de un ranking guardado con otras reglas (HU-29 escenario 8; HU-30).

Código puro y determinístico, sin base de datos. Cada entrada del ranking se recalcula desde su
instantánea (`scoring_inputs_from_snapshot`) con el motor único (`engine.calculate_score`), y
el conjunto se reordena con el desempate de la regla 5 tomado de la misma instantánea
(`ranking_candidate_from_snapshot`). Con las reglas del ranking, el resultado es idéntico a lo
guardado (escenario 9). El desglose por factor usa `PillarSimulator`, que reusa los pilares del
mismo motor y da exactamente lo mismo (escenario 22).
"""

import uuid
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Any

from .engine import (
    PILLAR_PARAMETERS,
    Pillars,
    ScoreResult,
    ScoringInputs,
    ScoringParameters,
    calculate_score,
    combine_pillars,
    pillar,
    pillar_inputs,
)
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
    """Cómo se mueven las posiciones frente al ranking (escenario 13).

    `up + down + unchanged` es la población. Los relevantes son un subconjunto de `up` y de
    `down`: cambian al menos `relevant_threshold` posiciones.
    """

    up: int
    down: int
    unchanged: int
    # Promedio exacto de |cambio de posición|; se muestra con un decimal.
    mean_abs_position_change: Decimal
    relevant_threshold: int
    relevant_up: int
    relevant_down: int


def simulate_entries(
    entries: Sequence[StoredEntry], params: ScoringParameters
) -> list[SimulatedEntry]:
    """Recalcula cada entrada y les da posición. Devuelve una por entrada, en el mismo orden.

    La población es exactamente la de `entries`: ni se agregan ni se quitan socios. Es el
    cálculo completo, sin atajos: la referencia de la paridad del escenario 22.
    """
    scores = [
        calculate_score(scoring_inputs_from_snapshot(entry.snapshot), params)
        for entry in entries
    ]
    return _positioned(entries, scores)


def _positioned(
    entries: Sequence[StoredEntry], scores: Sequence[ScoreResult]
) -> list[SimulatedEntry]:
    """Ordena con el desempate de la instantánea (regla 5) y arma las entradas simuladas."""
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


# --- Atajo por pilares y tiempo máximo (escenarios 21 y 22) --------------------------------

# Cada cuántos socios se mira el reloj dentro de un recálculo.
CHECK_EVERY = 1000
# SC-006: el desglose tiene 9 s hasta 50.000 socios y 30 s hasta 500.000.
SMALL_CLUB = 50_000
SMALL_CLUB_BUDGET = 9
LARGE_CLUB_BUDGET = 30

Checkpoint = Callable[[], None]


def _no_check() -> None:
    """Sin tiempo máximo."""


class BreakdownTimeout(Exception):
    """El desglose superó su tiempo máximo (escenario 21)."""


def breakdown_budget(population: int) -> int:
    """Segundos que tiene el desglose para un ranking de `population` socios (SC-006)."""
    return SMALL_CLUB_BUDGET if population <= SMALL_CLUB else LARGE_CLUB_BUDGET


class Deadline:
    """Un tiempo máximo medido con un reloj monótono inyectable (en segundos)."""

    def __init__(self, seconds: float, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._ends_at = clock() + seconds

    def check(self) -> None:
        if self._clock() > self._ends_at:
            raise BreakdownTimeout


class PillarSimulator:
    """Recalcula un mismo ranking con varios juegos de valores, reusando los pilares.

    Cada pilar se calcula una sola vez por cada combinación de los parámetros de los que
    depende (`engine.PILLAR_PARAMETERS`): cambiar los pesos o `αA` solo recombina, y cambiar
    `dsat` recalcula solo la distancia. Dentro de cada cálculo, socios con los mismos insumos
    del pilar (`engine.pillar_inputs`) comparten su valor. Como `calculate_score` es por definición
    `combine_pillars(score_pillars(...))`, el resultado es idéntico a `simulate_entries`
    (escenario 22, test de paridad). `checkpoint` se llama cada `CHECK_EVERY` socios.
    """

    def __init__(
        self, entries: Sequence[StoredEntry], checkpoint: Checkpoint = _no_check
    ) -> None:
        self._entries = list(entries)
        self._check = checkpoint
        self._inputs: list[ScoringInputs] = []
        for index, entry in enumerate(self._entries):
            self._tick(index)
            self._inputs.append(scoring_inputs_from_snapshot(entry.snapshot))
        self._columns: dict[tuple[Any, ...], list[Decimal]] = {}

    def _tick(self, index: int) -> None:
        if index % CHECK_EVERY == 0:
            self._check()

    def _column(self, name: str, params: ScoringParameters) -> list[Decimal]:
        key = (name, *(getattr(params, p) for p in PILLAR_PARAMETERS[name]))
        if key not in self._columns:
            # Socios con los mismos insumos del pilar comparten su valor.
            known: dict[Hashable, Decimal] = {}
            column = []
            for index, inputs in enumerate(self._inputs):
                self._tick(index)
                same = pillar_inputs(name, inputs)
                if same not in known:
                    known[same] = pillar(name, inputs, params)
                column.append(known[same])
            self._columns[key] = column
        return self._columns[key]

    def run(self, params: ScoringParameters) -> list[SimulatedEntry]:
        columns = {name: self._column(name, params) for name in PILLAR_PARAMETERS}
        scores = []
        for index in range(len(self._inputs)):
            self._tick(index)
            pillars = Pillars(**{name: c[index] for name, c in columns.items()})
            scores.append(combine_pillars(pillars, params))
        return _positioned(self._entries, scores)


def position_change(before: StoredEntry, after: SimulatedEntry) -> int:
    """`posición del ranking − posición simulada`: positivo sube, negativo baja."""
    return before.position - after.position


def relevant_threshold(population: int) -> int:
    """`m = max(1, ceil(N / 100))`: el 1 % del ranking, fijo en el producto (también HU-30)."""
    return max(1, -(-population // 100))


def movement(
    before: Sequence[StoredEntry], after: Sequence[SimulatedEntry]
) -> Movement:
    """Suben, bajan, sin cambio, cambio absoluto medio y movimientos relevantes.

    `after` viene en el orden de `before` (`simulate_entries`). Sube relevante un cambio
    `≥ +m`; baja relevante uno `≤ −m`.
    """
    changes = [position_change(b, a) for b, a in zip(before, after, strict=True)]
    m = relevant_threshold(len(changes))
    return Movement(
        up=sum(1 for c in changes if c > 0),
        down=sum(1 for c in changes if c < 0),
        unchanged=sum(1 for c in changes if c == 0),
        mean_abs_position_change=(
            Decimal(sum(abs(c) for c in changes)) / len(changes)
            if changes
            else Decimal(0)
        ),
        relevant_threshold=m,
        relevant_up=sum(1 for c in changes if c >= m),
        relevant_down=sum(1 for c in changes if c <= -m),
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


# --- Efecto de cada factor por separado (escenario 18) -------------------------------------

# Los factores que se simulan solos; "otros parámetros" nunca se aísla.
ISOLATED_FACTORS: tuple[str, ...] = (PILLAR_WEIGHTS, "alpha_a", "d_sat")


def factors_to_isolate(factors: Sequence[str]) -> list[str]:
    """Factores que llevan una simulación propia: solo si cambiaron dos o más factores, y solo
    entre pesos de los pilares, `αA` y `dsat` (como mucho tres simulaciones más)."""
    if len(factors) < 2:
        return []
    return [factor for factor in ISOLATED_FACTORS if factor in factors]


def isolated_values(
    before: Mapping[str, Decimal], hypothetical: Mapping[str, Decimal], factor: str
) -> dict[str, Decimal]:
    """Los valores del ranking con solo los de `factor` tomados de los hipotéticos.

    Siguen siendo válidos: los tres pesos vienen siempre del mismo juego de valores (los dos
    suman 1) y cada valor suelto ya pasó sus límites.
    """
    return {
        key: hypothetical[key] if factor_of(key) == factor else value
        for key, value in before.items()
    }


def mean_total_change(
    before: Sequence[StoredEntry], after: Sequence[SimulatedEntry]
) -> Fraction:
    """Cambio exacto del total medio (simulación − ranking), sobre los mismos socios."""
    if len(before) != len(after) or not before:
        raise ValueError("Las dos situaciones necesitan los mismos socios.")
    difference = sum((a.total - b.total for b, a in zip(before, after)), Decimal(0))
    return Fraction(difference) / len(before)


@dataclass(frozen=True)
class FactorEffect:
    """Lo que mueve un factor por sí solo frente al ranking."""

    factor: str
    parameters: tuple[str, ...]
    mean_total_change: Fraction
    movement: Movement


def rank_effects(effects: Sequence[FactorEffect]) -> list[FactorEffect]:
    """De mayor a menor cambio absoluto medio de posición; empate: el orden de `FACTORS`.

    Todas las simulaciones tienen los mismos `N` socios: comparar los promedios es comparar
    sumas de enteros, sin pérdida.
    """
    return sorted(
        effects,
        key=lambda e: (-e.movement.mean_abs_position_change, FACTORS.index(e.factor)),
    )


def remainder_change(
    full_change: Fraction, effects: Sequence[FactorEffect]
) -> Fraction:
    """Escenario 19: cambio del total medio de la simulación completa menos la suma de los
    aislados. Junta los otros parámetros y las interacciones: los efectos no se suman."""
    return full_change - sum((e.mean_total_change for e in effects), Fraction(0))

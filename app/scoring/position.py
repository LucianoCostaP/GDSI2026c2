"""Posición estimada del simulador para un Partido (HU-18, "Position model").

Código puro y determinístico. Cada otro socio `j` tiene dos totales oficiales para el Partido,
si asiste (`A_j`) y si no (`B_j`), y asiste con probabilidad `p_j`, su tasa histórica de la
clase suavizada hacia la tasa del club. La posición estimada es 1 más la suma de las
probabilidades de que cada otro socio termine arriba; el rango es normal con nivel configurable.

Las probabilidades se suman como fracciones exactas, así que el puesto estimado no depende del
orden de los socios. Solo la raíz de la dispersión y el cuantil normal son de punto flotante.
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from statistics import NormalDist


@dataclass(frozen=True)
class OtherOutcome:
    """Un otro socio frente a una hipótesis del que consulta."""

    probability: Fraction  # p_j: que asista al Partido
    above_if_attends: bool  # [A_j arriba]
    above_if_skips: bool  # [B_j arriba]


@dataclass(frozen=True)
class PositionRange:
    estimate: int
    lower: int
    upper: int


def club_rate(
    history: Iterable[tuple[Mapping[str, int], Mapping[str, int]]], match_class: str
) -> Fraction | None:
    """`r`: asistidos / contados de la clase, sumados sobre todos los socios del ranking.

    `history` trae, por socio, `(attended_by_class, matches_by_class)`. Si el club no tiene
    ningún partido contado de la clase, se usa la tasa de todas las clases; si no tiene ninguno,
    `None` (la posición no se estima: `INSUFFICIENT_HISTORY`).
    """
    attended_class = counted_class = attended_all = counted_all = 0
    for attended, counted in history:
        attended_class += attended.get(match_class, 0)
        counted_class += counted.get(match_class, 0)
        attended_all += sum(attended.values())
        counted_all += sum(counted.values())
    if counted_class:
        return Fraction(attended_class, counted_class)
    if counted_all:
        return Fraction(attended_all, counted_all)
    return None


def attendance_probability(
    attended: int, counted: int, rate: Fraction, prior_strength: Decimal
) -> Fraction:
    """`p_j = (a_j + k·r) / (n_j + k)`."""
    k = Fraction(prior_strength)
    return (attended + k * rate) / (counted + k)


def z_for_level(level: Decimal) -> float:
    """Cuantil normal de dos colas del nivel del rango (0,80 → 1,2816)."""
    if not Decimal(0) < level < Decimal(1):
        raise ValueError(f"Nivel de rango inválido: {level}")
    return NormalDist().inv_cdf((1 + float(level)) / 2)


def estimate_position(
    others: Sequence[OtherOutcome], population: int, z: float
) -> PositionRange:
    """Puesto estimado (1 + μ, redondeado hacia arriba en .5) y rango recortado a [1, N]."""
    mu = Fraction(0)
    variance = Fraction(0)
    for other in others:
        p = other.probability
        mu += p * other.above_if_attends + (1 - p) * other.above_if_skips
        # Solo suman dispersión los que quedan arriba si asisten y abajo si no (A_j ≥ B_j).
        if other.above_if_attends and not other.above_if_skips:
            variance += p * (1 - p)
    center = 1 + mu
    spread = z * math.sqrt(variance)
    return PositionRange(
        estimate=math.floor(center + Fraction(1, 2)),
        lower=max(1, math.floor(float(center) - spread)),
        upper=min(population, math.ceil(float(center) + spread)),
    )

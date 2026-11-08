"""Distribución de los totales de un ranking (HU-29 escenarios 11, 12 y 14).

Código puro y determinístico. Trabaja sobre los totales de 2 decimales (regla 1 del modelo de
puntaje), tal como se guardan o como los devuelve el motor. Los valores son exactos; redondear
para mostrar es cosa de quien los presenta ("Calculation definitions" del spec de HU-29).
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext

# --- Histograma (escenario 11) -------------------------------------------------------------

BIN_WIDTH = 5
BIN_COUNT = 20
_FULL_SCORE = Decimal(100)


@dataclass(frozen=True)
class Bin:
    """Un bin fijo: `[lower, upper)`, salvo el último, `[95, 100]`, que incluye el 100."""

    lower: int
    upper: int

    @property
    def label(self) -> str:
        closing = "]" if self.upper == BIN_WIDTH * BIN_COUNT else ")"
        return f"[{self.lower},{self.upper}{closing}"


BINS: tuple[Bin, ...] = tuple(
    Bin(lower=i * BIN_WIDTH, upper=(i + 1) * BIN_WIDTH) for i in range(BIN_COUNT)
)


def bin_index(total: Decimal) -> int:
    """Bin de un total entre 0 y 100. Un total de exactamente 100 cae en el último."""
    if not Decimal(0) <= total <= _FULL_SCORE:
        raise ValueError(f"Total fuera de [0, 100]: {total}")
    return min(int(total // BIN_WIDTH), BIN_COUNT - 1)


def histogram(totals: Sequence[Decimal]) -> list[int]:
    """Cantidad de socios en cada uno de los 20 bins; la suma es `len(totals)`."""
    counts = [0] * BIN_COUNT
    for total in totals:
        counts[bin_index(total)] += 1
    return counts


# --- Media, mediana, desvío y percentiles (escenario 12) -----------------------------------

_CENTS = Decimal(100)
# Precisión de sobra para la media y la raíz del desvío: ningún redondeo intermedio llega a
# afectar el segundo decimal.
_PRECISION = 40


@dataclass(frozen=True)
class Summary:
    """Estadísticas exactas de los totales."""

    mean: Decimal
    median: Decimal
    std_dev: Decimal
    p10: Decimal
    p90: Decimal

    def minus(self, other: "Summary") -> "Summary":
        """Diferencia campo a campo (`self − other`), con los valores exactos."""
        return Summary(
            mean=self.mean - other.mean,
            median=self.median - other.median,
            std_dev=self.std_dev - other.std_dev,
            p10=self.p10 - other.p10,
            p90=self.p90 - other.p90,
        )


def percentile(ordered: Sequence[Decimal], p: int) -> Decimal:
    """Rango más cercano: el total en la posición `ceil(p/100 · N)` de los totales ordenados."""
    rank = -(-p * len(ordered) // 100)
    return ordered[max(rank, 1) - 1]


def median(ordered: Sequence[Decimal]) -> Decimal:
    """El total del medio; con `N` par, el promedio de los dos del medio."""
    n = len(ordered)
    middle = n // 2
    if n % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def summary(totals: Sequence[Decimal]) -> Summary:
    """Media, mediana, desvío poblacional (divisor `N`) y percentiles 10 y 90.

    Los totales tienen 2 decimales, así que la media y la varianza salen de sumas enteras de
    centavos: `σ = √(N·Σc² − (Σc)²) / (100·N)`, sin acumular errores de redondeo.
    """
    if not totals:
        raise ValueError("No hay totales: el ranking no tiene socios.")
    n = len(totals)
    cents = [int(total * _CENTS) for total in totals]
    if any(
        Decimal(c) != total * _CENTS for c, total in zip(cents, totals, strict=True)
    ):
        raise ValueError("Los totales tienen que tener 2 decimales.")
    sum_cents = sum(cents)
    spread = n * sum(c * c for c in cents) - sum_cents * sum_cents
    ordered = sorted(totals)
    with localcontext() as context:
        context.prec = _PRECISION
        mean = Decimal(sum_cents) / (_CENTS * n)
        std_dev = Decimal(spread).sqrt() / (_CENTS * n)
    return Summary(
        mean=mean,
        median=median(ordered),
        std_dev=std_dev,
        p10=percentile(ordered, 10),
        p90=percentile(ordered, 90),
    )


# --- Saturación y empates (escenario 14) ---------------------------------------------------


@dataclass(frozen=True)
class Saturation:
    """Socios en el tope, con ajuste por tope y empatados."""

    # Total igual a 100,00.
    at_cap: int
    # Componente `cap_adjustment` menor que 0: sus componentes sumaban más de 100.
    needs_cap_adjustment: int
    # Socios cuyo total coincide con el de al menos otro socio.
    tied: int
    # Tamaño del grupo empatado más grande; 0 si no hay empates.
    largest_tie: int


def saturation(
    totals: Sequence[Decimal], cap_adjustments: Sequence[Decimal]
) -> Saturation:
    """Cuenta sobre los totales de 2 decimales y el ajuste por tope de cada socio."""
    if len(totals) != len(cap_adjustments):
        raise ValueError("Hace falta un ajuste por tope por cada total.")
    groups = [size for size in Counter(totals).values() if size > 1]
    return Saturation(
        at_cap=sum(1 for total in totals if total == _FULL_SCORE),
        needs_cap_adjustment=sum(1 for adjustment in cap_adjustments if adjustment < 0),
        tied=sum(groups),
        largest_tie=max(groups, default=0),
    )

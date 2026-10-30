"""Componentes del puntaje de un socio (modelo de scoring, regla 3).

Código puro. Define los seis componentes que guarda cada entrada del ranking y cómo se
suman. El cálculo de cada uno llega con el motor de scoring (Ciclo 0 y Ciclo 3 de HU-25).
"""

from collections.abc import Mapping
from decimal import Decimal

COMPONENT_KEYS: tuple[str, ...] = (
    "attendance_frequency",
    "attendance_distance",
    "institutional",
    "seniority_age",
    "new_member_bonus",
    "cap_adjustment",
)

_ZERO = Decimal("0.00")


def empty_components() -> dict[str, Decimal]:
    """Los seis componentes en cero, con dos decimales."""
    return {key: _ZERO for key in COMPONENT_KEYS}


def total_of(components: Mapping[str, Decimal]) -> Decimal:
    """Total del socio: la suma de sus componentes (que ya vienen redondeados).

    Exige exactamente los seis componentes: un faltante o uno desconocido es un error de
    programación, no un dato a ignorar.
    """
    if set(components) != set(COMPONENT_KEYS):
        raise ValueError(
            f"Se esperaban los componentes {COMPONENT_KEYS}, llegaron {tuple(components)}."
        )
    return sum(components.values(), _ZERO)
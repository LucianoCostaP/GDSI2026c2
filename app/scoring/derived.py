"""Valores derivados de una fórmula, para mostrar (HU-29 escenario 1).

Código puro. Los valores derivados (por ejemplo `b` del modelo v1) no son parámetros: el Admin
no los edita, se calculan a partir de los parámetros y se muestran como solo lectura. El cálculo
sale del motor (`engine`), así el valor mostrado es el mismo que usa el puntaje.
"""

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal

from .catalog import SCORING_MODEL_V1, FormulaDescriptor
from .engine import distance_slope

# Decimales con que se muestra un valor derivado (solo presentación; el motor usa el exacto).
DISPLAY_PLACES = Decimal("0.000001")


def _for_display(value: Decimal) -> Decimal:
    return value.quantize(DISPLAY_PLACES, rounding=ROUND_HALF_UP)


def derived_values(
    descriptor: FormulaDescriptor, values: Mapping[str, Decimal]
) -> dict[str, Decimal]:
    """Valor de cada derivado de la fórmula (por símbolo) con esos parámetros.

    Una fórmula sin cálculo conocido para sus derivados devuelve un diccionario vacío: el
    front muestra entonces solo la expresión.
    """
    if (descriptor.id, descriptor.version) == (
        SCORING_MODEL_V1.id,
        SCORING_MODEL_V1.version,
    ):
        return {"b": _for_display(distance_slope(values["d_sat"]))}
    return {}

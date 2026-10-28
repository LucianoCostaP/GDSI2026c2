"""Validación de los valores de una fórmula contra su descriptor.

La usan HU-27 (publicación y vista previa) y HU-28 (ajuste de parámetros): una sola
implementación, con aritmética decimal (nunca coma flotante binaria).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .catalog import FormulaDescriptor
from .formatting import format_decimal

MISSING = "PARAMETER_MISSING"
UNKNOWN = "PARAMETER_UNKNOWN"
NOT_A_NUMBER = "PARAMETER_NOT_A_NUMBER"
OUT_OF_LIMITS = "PARAMETER_OUT_OF_LIMITS"
SUM_VIOLATED = "SUM_CONSTRAINT_VIOLATED"


@dataclass(frozen=True)
class Violation:
    code: str
    message: str
    parameter: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    # Solo está completo si no hay violaciones: nunca se rellena con valores por defecto.
    values: dict[str, Decimal]
    violations: tuple[Violation, ...]

    @property
    def valid(self) -> bool:
        return not self.violations


def parse_decimal(raw: Any) -> Decimal | None:
    """Convierte un valor recibido a decimal; `None` si no es un número finito."""
    if isinstance(raw, bool):
        return None
    try:
        if isinstance(raw, int | Decimal):
            value = Decimal(raw)
        elif isinstance(raw, float):
            value = Decimal(repr(raw))
        elif isinstance(raw, str):
            value = Decimal(raw.strip().replace(",", "."))
        else:
            return None
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def validate_values(
    descriptor: FormulaDescriptor, raw: Mapping[str, Any]
) -> ValidationResult:
    violations: list[Violation] = []
    parsed: dict[str, Decimal] = {}

    for param in descriptor.parameters:
        given = raw.get(param.key)
        if given is None or (isinstance(given, str) and not given.strip()):
            violations.append(
                Violation(MISSING, f"Falta el valor de «{param.name}».", param.key)
            )
            continue
        value = parse_decimal(given)
        if value is None:
            violations.append(
                Violation(
                    NOT_A_NUMBER,
                    f"El valor de «{param.name}» tiene que ser un número.",
                    param.key,
                )
            )
            continue
        parsed[param.key] = value
        if not param.minimum <= value <= param.maximum:
            unit = f" {param.unit}" if param.unit else ""
            violations.append(
                Violation(
                    OUT_OF_LIMITS,
                    f"«{param.name}» tiene que estar entre {format_decimal(param.minimum)} "
                    f"y {format_decimal(param.maximum)}{unit}.",
                    param.key,
                )
            )

    for constraint in descriptor.constraints:
        if all(key in parsed for key in constraint.parameters):
            total = sum((parsed[key] for key in constraint.parameters), Decimal(0))
            if total != constraint.total:
                violations.append(
                    Violation(
                        SUM_VIOLATED,
                        f"{constraint.label} tienen que sumar {format_decimal(constraint.total)}; "
                        f"hoy suman {format_decimal(total)}.",
                    )
                )

    known = {p.key for p in descriptor.parameters}
    for key in raw:
        if key not in known:
            violations.append(
                Violation(
                    UNKNOWN, f"«{key}» no es un parámetro de esta fórmula.", str(key)
                )
            )

    return ValidationResult(parsed if not violations else {}, tuple(violations))

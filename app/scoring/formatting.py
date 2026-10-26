"""Formato de números para los textos en español (Argentina)."""

from decimal import Decimal


def decimal_to_str(value: Decimal) -> str:
    """Forma canónica para guardar y enviar un decimal: sin exponente ni ceros de más."""
    return format(value.normalize(), "f")


def format_decimal(value: Decimal) -> str:
    """Número para mostrar: coma decimal, sin separador de miles (`0,2`, `1200`)."""
    return decimal_to_str(value).replace(".", ",")


def format_percent(value: Decimal) -> str:
    """Una fracción como porcentaje: `0.6` -> `60 %`."""
    return f"{format_decimal(value * 100)} %"

"""Formato de números para los textos en español (Argentina)."""

from decimal import ROUND_HALF_UP, Decimal


def decimal_to_str(value: Decimal) -> str:
    """Forma canónica para guardar y enviar un decimal: sin exponente ni ceros de más."""
    return format(value.normalize(), "f")


def decimal_fixed(value: Decimal, places: int) -> str:
    """Para mostrar con una cantidad fija de decimales, mitad hacia arriba: `46.9` -> `46.90`.

    Nunca devuelve `-0.00`: un valor que redondea a cero sale sin signo.
    """
    rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return format(rounded if rounded else abs(rounded), "f")


def format_decimal(value: Decimal) -> str:
    """Número para mostrar: coma decimal, sin separador de miles (`0,2`, `1200`)."""
    return decimal_to_str(value).replace(".", ",")


def format_percent(value: Decimal) -> str:
    """Una fracción como porcentaje: `0.6` -> `60 %`."""
    return f"{format_decimal(value * 100)} %"

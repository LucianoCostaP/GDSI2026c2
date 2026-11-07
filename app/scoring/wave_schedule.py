"""Cronograma de habilitación de las olas (HU-37). Funciones puras, sin base de datos.

El Admin define la apertura de la primera ola y el cierre general; con N olas, la ola i
empieza en apertura + (i − 1) × (cierre − apertura) / N.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class PeriodViolation:
    code: str
    message: str


def _waves_label(waves: int) -> str:
    return "1 oleada" if waves == 1 else f"{waves} oleadas"


def validate_period(
    *,
    opening: datetime,
    closing: datetime,
    event_start: datetime,
    waves: int,
    now: datetime,
    min_step_minutes: int,
) -> PeriodViolation | None:
    """La primera regla que no se cumple, o `None` si el período es válido.

    Orden: apertura futura, cierre posterior a la apertura, cierre no posterior al inicio
    del evento y paso mínimo entre oleadas. El paso se compara sin dividir
    (cierre − apertura ≥ N × mínimo) para no arrastrar redondeos.
    """
    if opening <= now:
        return PeriodViolation(
            "OPENING_NOT_IN_FUTURE",
            "La apertura tiene que ser posterior a este momento.",
        )
    if closing <= opening:
        return PeriodViolation(
            "CLOSING_NOT_AFTER_OPENING",
            "El cierre tiene que ser posterior a la apertura.",
        )
    if closing > event_start:
        return PeriodViolation(
            "CLOSING_AFTER_EVENT_START",
            "El cierre no puede ser posterior al inicio del partido.",
        )
    if closing - opening < waves * timedelta(minutes=min_step_minutes):
        return PeriodViolation(
            "WAVE_STEP_TOO_SHORT",
            f"Entre oleadas tiene que haber al menos {min_step_minutes} minutos: con "
            f"{_waves_label(waves)}, el período tiene que durar al menos "
            f"{waves * min_step_minutes} minutos.",
        )
    return None

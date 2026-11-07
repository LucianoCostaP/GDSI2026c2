"""Cronograma de habilitación de las olas (HU-37). Funciones puras, sin base de datos.

El Admin define la apertura de la primera ola y el cierre general; con N olas, la ola i
empieza en apertura + (i − 1) × (cierre − apertura) / N.
"""

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta

from .waves import Wave


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


@dataclass(frozen=True)
class ScheduledWave:
    wave: Wave
    starts_at: datetime


def wave_starts(opening: datetime, closing: datetime, waves: int) -> list[datetime]:
    """Hora de inicio de cada ola, en orden: la ola 1 (mejores posiciones) abre primero.

    Se multiplica antes de dividir para que el redondeo (al microsegundo) no se acumule.
    """
    if waves < 1:
        raise ValueError("waves tiene que ser al menos 1")
    period = closing - opening
    return [opening + period * (order - 1) / waves for order in range(1, waves + 1)]


def schedule_waves(
    waves: list[Wave], opening: datetime, closing: datetime
) -> list[ScheduledWave]:
    """Las olas de la segmentación con su hora de inicio."""
    starts = wave_starts(opening, closing, len(waves))
    return [
        ScheduledWave(wave, starts_at)
        for wave, starts_at in zip(waves, starts, strict=True)
    ]


def step_seconds(opening: datetime, closing: datetime, waves: int) -> int:
    """Tiempo entre la apertura de dos olas seguidas, en segundos enteros."""
    return int((closing - opening).total_seconds()) // waves


class WaveState(enum.StrEnum):
    # Todavía no llegó su hora de inicio.
    PENDING = "pending"
    # Ya llegó su hora y no pasó el cierre general: el acceso está abierto.
    OPEN = "open"
    # Pasó el cierre general.
    CLOSED = "closed"


def wave_state(starts_at: datetime, closing: datetime, now: datetime) -> WaveState:
    """Una ola abre en su hora de inicio y queda abierta hasta el cierre general."""
    if now >= closing:
        return WaveState.CLOSED
    if now >= starts_at:
        return WaveState.OPEN
    return WaveState.PENDING


def wave_states(
    starts: list[datetime], closing: datetime, now: datetime
) -> list[WaveState]:
    """Estado de cada ola. Como las horas de inicio están en orden, cuando abre una ola
    también están abiertas todas las anteriores (escenario 5, FR-004)."""
    return [wave_state(starts_at, closing, now) for starts_at in starts]


def first_wave_open(opening: datetime, now: datetime) -> bool:
    """Si la primera ola ya abrió: desde la apertura, aunque después llegue el cierre."""
    return now >= opening

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
    waves: list[Wave],
    opening: datetime,
    closing: datetime,
    merged_into_order: int | None = None,
) -> list[ScheduledWave]:
    """Las olas de la segmentación con su hora de inicio. `closing` es el cierre con el que
    se generó el cronograma; con `merged_into_order`, las olas fusionadas por una
    reprogramación (HU-23B) toman la hora de la ola a la que se sumaron."""
    starts = effective_wave_starts(opening, closing, len(waves), merged_into_order)
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


# ==============================================================================
# HU-23B US3: ajuste del cronograma cuando se reprograma el Partido
# ==============================================================================


def effective_wave_starts(
    opening: datetime,
    generated_closing: datetime,
    waves: int,
    merged_into_order: int | None,
) -> list[datetime]:
    """Hora de inicio de cada ola después de los ajustes (HU-23B, Key Entities).

    Las horas se siguen derivando de la apertura y del cierre con el que se generó el
    cronograma, así que un ajuste nunca mueve una ola que no se fusionó. Con
    `merged_into_order = k`, las olas k+1 a N toman la hora de la ola k.
    """
    starts = wave_starts(opening, generated_closing, waves)
    if merged_into_order is None:
        return starts
    target = starts[merged_into_order - 1]
    return [
        target if order > merged_into_order else starts_at
        for order, starts_at in enumerate(starts, start=1)
    ]


def effective_order(order: int, merged_into_order: int | None) -> int:
    """La ola a la que pertenece hoy la ola `order`: la misma, o la ola en la que se fusionó."""
    if merged_into_order is not None and order > merged_into_order:
        return merged_into_order
    return order


class ScheduleEffect(enum.StrEnum):
    # El Partido no tiene cronograma (con o sin olas): solo cambia el evento.
    NO_SCHEDULE = "no_schedule"
    # El cierre general no es posterior al nuevo inicio: el cronograma queda como está.
    NONE = "none"
    # Ninguna ola queda afectada: solo el cierre general pasa al nuevo inicio.
    CLOSING_ADJUSTED = "closing_adjusted"
    # Las olas afectadas se suman a la última que no lo está; el cierre pasa al nuevo inicio.
    WAVES_MERGED = "waves_merged"
    # Todas las olas quedan afectadas, o es un borrador solapado: hay que generarlo de nuevo.
    INVALIDATED = "invalidated"


@dataclass(frozen=True)
class RescheduleImpact:
    effect: ScheduleEffect
    # Cierre general efectivo antes y después (iguales si no cambia).
    previous_closing: datetime | None = None
    new_closing: datetime | None = None
    # La última ola separada después del ajuste (`None` si no hay ninguna fusión).
    merged_into_order: int | None = None
    # Olas de la segmentación que se mueven con esta reprogramación (k+1 a N).
    moved_orders: tuple[int, ...] = ()
    # La ola a la que se suman ya abrió: sus socios tienen acceso en el momento.
    target_open: bool = False


def reschedule_impact(
    *,
    status: str,
    starts: list[datetime],
    closing: datetime,
    merged_into_order: int | None,
    new_start: datetime,
    now: datetime,
    min_step_minutes: int,
) -> RescheduleImpact:
    """Qué le pasa al cronograma si el Partido pasa a empezar en `new_start` (HU-23B US3).

    `starts` son las horas efectivas de las olas, `closing` el cierre efectivo y `status`
    el del cronograma (`draft`, `confirmed`, `invalidated`). Una ola está afectada si todavía
    no abrió y empieza después de `new_start − min_step`; como las horas están en orden, las
    afectadas son siempre las últimas.
    """
    unchanged = RescheduleImpact(
        ScheduleEffect.NONE, closing, closing, merged_into_order
    )
    # Escenario 2 (y uno ya invalidado, que no abre nada): el cronograma no cambia.
    if status == "invalidated" or closing <= new_start:
        return unchanged
    # Escenario 7: un borrador solapado se invalida (los socios nunca lo vieron).
    if status == "draft":
        return RescheduleImpact(ScheduleEffect.INVALIDATED, closing, None)

    limit = new_start - timedelta(minutes=min_step_minutes)
    affected = [now < starts_at and starts_at > limit for starts_at in starts]
    if not any(affected):
        # Escenario 3: solo el cierre general pasa al nuevo inicio.
        return RescheduleImpact(
            ScheduleEffect.CLOSING_ADJUSTED, closing, new_start, merged_into_order
        )
    if all(affected):
        # Escenario 6: ninguna abrió y la primera quedaría pegada o después del inicio.
        return RescheduleImpact(ScheduleEffect.INVALIDATED, closing, None)
    # Escenarios 4, 5 y 8: las afectadas se suman a la última no afectada.
    target = affected.index(True)
    return RescheduleImpact(
        ScheduleEffect.WAVES_MERGED,
        closing,
        new_start,
        target,
        tuple(range(target + 1, len(starts) + 1)),
        target_open=now >= starts[target - 1],
    )

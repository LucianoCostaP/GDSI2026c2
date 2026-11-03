"""Insumos de participación institucional de un socio (modelo de scoring, 2.2; HU-25 FR-009).

Código puro: sin base de datos ni reloj. Recibe lo que el socio hizo (eventos institucionales a
los que asistió y registros de actividades recurrentes) y arma los puntos crudos que el motor
topa con `Pinst_max` (Ciclo 0). También son la instantánea que guarda cada entrada.

- Vigencia móvil: cuenta lo que ocurrió dentro de los 365 días anteriores a la fecha de cálculo.
  Un registro de exactamente 365 días de antigüedad todavía cuenta; de 366, ya venció.
- Eventos: cada uno vale los puntos con los que se publicó (Vk), una sola vez por evento.
- Actividades: cada mes calendario en el que el socio estuvo activo dentro de la vigencia cuenta
  completo (no se prorratea). Los meses se unen entre los registros de una misma actividad, así
  que dos registros que se pisan no suman dos veces. Cada actividad tiene un tope de 12 meses.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

VALIDITY_DAYS = 365
MAX_ACTIVITY_MONTHS = 12
# Puntos por mes de cada actividad: constantes de la fórmula, no editables.
POINTS_PER_MONTH: dict[str, int] = {"deporte_federado": 10, "subcomision": 15}


@dataclass(frozen=True)
class InstitutionalEvent:
    """Evento institucional al que el socio asistió. `day` es la fecha en hora de Buenos Aires."""

    event_id: str
    day: date
    points: int

    def __post_init__(self) -> None:
        if self.points <= 0:
            raise ValueError(
                f"Los puntos del evento tienen que ser positivos: {self.points}."
            )


@dataclass(frozen=True)
class ActivityRecord:
    """Período de actividad recurrente del socio (`kind` es la clave de `POINTS_PER_MONTH`)."""

    kind: str
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.kind not in POINTS_PER_MONTH:
            raise ValueError(f"Actividad desconocida: {self.kind!r}.")
        if self.end < self.start:
            raise ValueError("La actividad termina antes de empezar.")


@dataclass(frozen=True)
class InstitutionalInputs:
    """Puntos institucionales crudos de un socio, antes del tope `Pinst_max`."""

    window_start: date
    events: tuple[InstitutionalEvent, ...]
    activity_months: dict[str, int]

    @property
    def event_points(self) -> int:
        """Σ Vk·Ak."""
        return sum(event.points for event in self.events)

    @property
    def activity_points(self) -> int:
        """Σ Dm·tm."""
        return sum(
            POINTS_PER_MONTH[kind] * months
            for kind, months in self.activity_months.items()
        )

    @property
    def points(self) -> int:
        return self.event_points + self.activity_points

    def as_dict(self) -> dict[str, Any]:
        """Forma serializable (JSON) para la instantánea de la entrada."""
        return {
            "window_start": self.window_start.isoformat(),
            "events": [
                {"event_id": e.event_id, "points": e.points} for e in self.events
            ],
            "event_points": self.event_points,
            "activity_months": dict(self.activity_months),
            "activity_points": self.activity_points,
            "points": self.points,
        }


def institutional_window_start(calculation_date: date) -> date:
    """Primer día que todavía cuenta: 365 días antes de la fecha de cálculo."""
    return calculation_date - timedelta(days=VALIDITY_DAYS)


def _months_between(start: date, end: date) -> Iterator[tuple[int, int]]:
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def build_institutional_inputs(
    *,
    calculation_date: date,
    attended_events: Iterable[InstitutionalEvent],
    activities: Iterable[ActivityRecord],
) -> InstitutionalInputs:
    """Arma los puntos institucionales de un socio.

    `attended_events` son los eventos institucionales con un registro de asistencia del socio
    (Ak = 1); los que no vienen acá valen 0. Se descarta lo que cae fuera de la vigencia.
    """
    window_start = institutional_window_start(calculation_date)

    counted: dict[str, InstitutionalEvent] = {}
    for event in attended_events:
        if window_start <= event.day <= calculation_date:
            counted.setdefault(event.event_id, event)

    months: dict[str, set[tuple[int, int]]] = {kind: set() for kind in POINTS_PER_MONTH}
    for activity in activities:
        start = max(activity.start, window_start)
        end = min(activity.end, calculation_date)
        if start <= end:
            months[activity.kind].update(_months_between(start, end))

    return InstitutionalInputs(
        window_start=window_start,
        events=tuple(sorted(counted.values(), key=lambda e: (e.day, e.event_id))),
        activity_months={
            kind: min(len(covered), MAX_ACTIVITY_MONTHS)
            for kind, covered in months.items()
        },
    )

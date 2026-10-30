"""Insumos de asistencia de un socio para el ranking (modelo de scoring, 2.1; HU-25 FR-008).

Código puro: sin base de datos ni reloj. Recibe los partidos ya filtrados por la capa de datos
(jugados y con asistencia cargada) y arma, para un socio, los datos crudos con los que el motor
calcula la frecuencia y la distancia (Ciclo 0). Esos mismos datos son la instantánea que guarda
cada entrada del ranking (regla 4 del modelo), así que HU-18 y HU-29 pueden recalcular con
otros parámetros sin releer las asistencias.

- Ventana: año calendario anterior completo más el año en curso hasta la fecha de cálculo.
- Denominador: solo cuentan los partidos desde `max(fecha de alta, inicio de la ventana)`.
- Un partido sin asistencia cargada nunca llega acá: se ignora, no es una ausencia.
"""

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

MATCH_CLASSES: tuple[str, ...] = ("A", "B", "C")


@dataclass(frozen=True)
class MatchEvent:
    """Un partido jugado y con asistencia cargada. `day` es la fecha en hora de Buenos Aires."""

    event_id: str
    day: date
    match_class: str

    def __post_init__(self) -> None:
        if self.match_class not in MATCH_CLASSES:
            raise ValueError(
                f"Clase de partido desconocida: {self.match_class!r}. "
                f"Se esperaba una de {MATCH_CLASSES}."
            )


@dataclass(frozen=True)
class AttendanceInputs:
    """Datos crudos de asistencia de un socio. Los conteos van por clase (A, B y C)."""

    window_start: date
    effective_start: date
    matches_by_class: dict[str, int]
    attended_by_class: dict[str, int]
    distance_km: Decimal

    @property
    def attended_matches(self) -> int:
        """N_asistidos del modelo: partidos a los que fue dentro del denominador."""
        return sum(self.attended_by_class.values())

    def as_dict(self) -> dict[str, Any]:
        """Forma serializable (JSON) para la instantánea de la entrada."""
        return {
            "window_start": self.window_start.isoformat(),
            "effective_start": self.effective_start.isoformat(),
            "matches_by_class": dict(self.matches_by_class),
            "attended_by_class": dict(self.attended_by_class),
            "attended_matches": self.attended_matches,
            "distance_km": str(self.distance_km),
        }


def attendance_window_start(calculation_date: date) -> date:
    """1 de enero del año anterior al de la fecha de cálculo."""
    return date(calculation_date.year - 1, 1, 1)


def _count_by_class(events: Iterable[MatchEvent]) -> dict[str, int]:
    counts = dict.fromkeys(MATCH_CLASSES, 0)
    for event in events:
        counts[event.match_class] += 1
    return counts


def build_attendance_inputs(
    *,
    alta: date,
    distance_km: Decimal,
    calculation_date: date,
    events: Sequence[MatchEvent],
    attended_event_ids: Collection[str],
) -> AttendanceInputs:
    """Arma los insumos de asistencia de un socio.

    `events` son los partidos jugados con asistencia cargada. Se cuentan los que caen entre
    `max(alta, inicio de la ventana)` y la fecha de cálculo, ambos inclusive. Una asistencia a
    un partido fuera de ese rango no suma: el numerador nunca supera al denominador.
    """
    window_start = attendance_window_start(calculation_date)
    effective_start = max(alta, window_start)
    counted = [e for e in events if effective_start <= e.day <= calculation_date]
    attended = [e for e in counted if e.event_id in attended_event_ids]
    return AttendanceInputs(
        window_start=window_start,
        effective_start=effective_start,
        matches_by_class=_count_by_class(counted),
        attended_by_class=_count_by_class(attended),
        distance_km=distance_km,
    )
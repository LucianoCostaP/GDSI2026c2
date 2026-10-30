"""HU-25, Ciclo 3a: insumos de asistencia (módulo puro, sin base de datos)."""

import json
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

import pytest

from app.scoring.attendance_inputs import (
    AttendanceInputs,
    MatchEvent,
    attendance_window_start,
    build_attendance_inputs,
)

CALCULATION_DATE = date(2026, 10, 29)
WINDOW_START = date(2025, 1, 1)


def match(event_id: str, day: date, match_class: str = "B") -> MatchEvent:
    return MatchEvent(event_id=event_id, day=day, match_class=match_class)


def build(
    *,
    alta: date = date(2010, 1, 1),
    events: Iterable[MatchEvent] = (),
    attended: Iterable[str] = (),
    distance: Decimal = Decimal("120.00"),
    calculation_date: date = CALCULATION_DATE,
) -> AttendanceInputs:
    return build_attendance_inputs(
        alta=alta,
        distance_km=distance,
        calculation_date=calculation_date,
        events=list(events),
        attended_event_ids=set(attended),
    )


# --- Ventana: 1 de enero del año anterior --------------------------------------------------


@pytest.mark.parametrize(
    ("calculation_date", "expected"),
    [
        (date(2026, 10, 29), date(2025, 1, 1)),
        (date(2026, 1, 1), date(2025, 1, 1)),
        (date(2026, 12, 31), date(2025, 1, 1)),
        (date(2027, 1, 1), date(2026, 1, 1)),
        (date(2024, 2, 29), date(2023, 1, 1)),
    ],
)
def test_window_start_is_jan_1_of_previous_year(
    calculation_date: date, expected: date
) -> None:
    assert attendance_window_start(calculation_date) == expected


def test_window_includes_its_first_day_and_excludes_the_day_before() -> None:
    inputs = build(
        events=[
            match("ANTES", date(2024, 12, 31), "C"),
            match("PRIMER-DIA", date(2025, 1, 1), "A"),
        ]
    )

    assert inputs.matches_by_class == {"A": 1, "B": 0, "C": 0}


def test_window_includes_the_calculation_date_and_excludes_the_day_after() -> None:
    inputs = build(
        events=[
            match("HOY", CALCULATION_DATE, "A"),
            match("MANIANA", date(2026, 10, 30), "C"),
        ]
    )

    assert inputs.matches_by_class == {"A": 1, "B": 0, "C": 0}


# --- Denominador: desde max(alta, inicio de la ventana) ------------------------------------


def test_denominator_starts_at_window_start_when_alta_is_older() -> None:
    inputs = build(alta=date(2010, 5, 20))

    assert inputs.window_start == WINDOW_START
    assert inputs.effective_start == WINDOW_START


def test_denominator_starts_at_alta_when_alta_is_inside_the_window() -> None:
    alta = date(2026, 3, 10)

    inputs = build(
        alta=alta,
        events=[
            match("ANTES-DEL-ALTA", date(2026, 3, 9), "A"),
            match("DIA-DEL-ALTA", alta, "B"),
            match("DESPUES", date(2026, 5, 1), "C"),
        ],
    )

    assert inputs.effective_start == alta
    assert inputs.matches_by_class == {"A": 0, "B": 1, "C": 1}


def test_alta_after_the_calculation_date_leaves_no_matches() -> None:
    inputs = build(alta=date(2026, 11, 1), events=[match("E1", date(2026, 10, 1))])

    assert inputs.matches_by_class == {"A": 0, "B": 0, "C": 0}


# --- Conteos por clase y asistidos ---------------------------------------------------------


def test_counts_matches_and_attended_by_class() -> None:
    events = [
        match("A1", date(2026, 2, 1), "A"),
        match("B1", date(2026, 3, 1), "B"),
        match("B2", date(2026, 4, 1), "B"),
        match("C1", date(2026, 5, 1), "C"),
    ]

    inputs = build(events=events, attended=["A1", "B2"])

    assert inputs.matches_by_class == {"A": 1, "B": 2, "C": 1}
    assert inputs.attended_by_class == {"A": 1, "B": 1, "C": 0}
    assert inputs.attended_matches == 2


def test_no_events_gives_zero_counts_for_every_class() -> None:
    inputs = build()

    assert inputs.matches_by_class == {"A": 0, "B": 0, "C": 0}
    assert inputs.attended_by_class == {"A": 0, "B": 0, "C": 0}
    assert inputs.attended_matches == 0


def test_attendance_outside_the_denominator_does_not_count() -> None:
    events = [
        match("ANTES-DEL-ALTA", date(2026, 1, 5), "A"),
        match("VALIDO", date(2026, 6, 5), "B"),
    ]

    inputs = build(
        alta=date(2026, 3, 1),
        events=events,
        attended=["ANTES-DEL-ALTA", "VALIDO", "DESCONOCIDO"],
    )

    assert inputs.attended_by_class == {"A": 0, "B": 1, "C": 0}
    assert inputs.attended_matches <= sum(inputs.matches_by_class.values())


def test_unknown_match_class_is_rejected() -> None:
    with pytest.raises(ValueError):
        MatchEvent(event_id="X", day=date(2026, 1, 1), match_class="D")


# --- Distancia y forma serializable --------------------------------------------------------


def test_distance_taken_from_socio() -> None:
    inputs = build(distance=Decimal("87.50"))

    assert inputs.distance_km == Decimal("87.50")
    assert inputs.as_dict()["distance_km"] == "87.50"


def test_as_dict_is_json_serializable_with_the_documented_shape() -> None:
    inputs = build(
        events=[match("B1", date(2026, 3, 1), "B")],
        attended=["B1"],
        distance=Decimal("120.00"),
    )

    data = json.loads(json.dumps(inputs.as_dict()))

    assert data == {
        "window_start": "2025-01-01",
        "effective_start": "2025-01-01",
        "matches_by_class": {"A": 0, "B": 1, "C": 0},
        "attended_by_class": {"A": 0, "B": 1, "C": 0},
        "attended_matches": 1,
        "distance_km": "120.00",
    }
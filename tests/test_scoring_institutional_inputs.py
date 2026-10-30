"""HU-25, Ciclo 3b: insumos de participación institucional (módulo puro, sin base de datos)."""

import json
from collections.abc import Iterable
from datetime import date, timedelta

import pytest

from app.scoring.institutional_inputs import (
    ActivityRecord,
    InstitutionalEvent,
    InstitutionalInputs,
    build_institutional_inputs,
    institutional_window_start,
)

CALCULATION_DATE = date(2026, 10, 29)
WINDOW_START = date(2025, 10, 29)  # 365 días antes


def event(event_id: str, day: date, points: int = 40) -> InstitutionalEvent:
    return InstitutionalEvent(event_id=event_id, day=day, points=points)


def activity(kind: str, start: date, end: date) -> ActivityRecord:
    return ActivityRecord(kind=kind, start=start, end=end)


def build(
    *,
    events: Iterable[InstitutionalEvent] = (),
    activities: Iterable[ActivityRecord] = (),
    calculation_date: date = CALCULATION_DATE,
) -> InstitutionalInputs:
    return build_institutional_inputs(
        calculation_date=calculation_date,
        attended_events=list(events),
        activities=list(activities),
    )


# --- Vigencia de 365 días ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("calculation_date", "expected"),
    [
        (date(2026, 10, 29), date(2025, 10, 29)),
        (date(2024, 3, 1), date(2023, 3, 2)),  # el año de 2024 es bisiesto
        (date(2026, 1, 1), date(2025, 1, 1)),
    ],
)
def test_validity_starts_365_days_before_the_calculation_date(
    calculation_date: date, expected: date
) -> None:
    assert institutional_window_start(calculation_date) == expected
    assert calculation_date - expected == timedelta(days=365)


def test_records_older_than_365_days_expire() -> None:
    inputs = build(
        events=[
            event("VENCIDO", WINDOW_START - timedelta(days=1), 50),
            event("ULTIMO-DIA", WINDOW_START, 40),
            event("FUTURO", CALCULATION_DATE + timedelta(days=1), 25),
        ],
        activities=[
            activity(
                "deporte_federado",
                date(2025, 1, 1),
                WINDOW_START - timedelta(days=1),
            ),
        ],
    )

    assert [e.event_id for e in inputs.events] == ["ULTIMO-DIA"]
    assert inputs.event_points == 40
    assert inputs.activity_months == {"deporte_federado": 0, "subcomision": 0}
    assert inputs.points == 40


def test_an_activity_ending_on_the_first_valid_day_still_counts_that_month() -> None:
    inputs = build(
        activities=[activity("deporte_federado", date(2025, 1, 1), WINDOW_START)]
    )

    assert inputs.activity_months["deporte_federado"] == 1
    assert inputs.points == 10


# --- Eventos institucionales ---------------------------------------------------------------


def test_institutional_event_uses_published_points() -> None:
    inputs = build(events=[event("ASAMBLEA", date(2026, 9, 1), 40)])

    assert inputs.event_points == 40
    assert inputs.points == 40


def test_event_points_add_up_event_by_event() -> None:
    inputs = build(
        events=[
            event("ELECCIONES", date(2026, 3, 1), 50),
            event("ASAMBLEA", date(2026, 9, 1), 40),
            event("ACTO", date(2026, 9, 15), 7),
        ]
    )

    assert inputs.event_points == 97
    assert [e.event_id for e in inputs.events] == ["ELECCIONES", "ASAMBLEA", "ACTO"]


def test_an_event_counts_once_even_if_it_comes_twice() -> None:
    inputs = build(
        events=[event("A", date(2026, 9, 1), 40), event("A", date(2026, 9, 1), 40)]
    )

    assert inputs.event_points == 40
    assert len(inputs.events) == 1


# --- Actividades recurrentes ---------------------------------------------------------------


def test_recurring_points_federated_10_subcommission_15() -> None:
    federated = build(
        activities=[activity("deporte_federado", date(2026, 8, 1), date(2026, 8, 31))]
    )
    subcommission = build(
        activities=[activity("subcomision", date(2026, 8, 1), date(2026, 8, 31))]
    )
    both = build(
        activities=[
            activity("deporte_federado", date(2026, 8, 1), date(2026, 9, 30)),
            activity("subcomision", date(2026, 9, 1), date(2026, 9, 30)),
        ]
    )

    assert federated.activity_points == 10
    assert subcommission.activity_points == 15
    assert both.activity_months == {"deporte_federado": 2, "subcomision": 1}
    assert both.activity_points == 35


def test_activity_months_capped_at_12() -> None:
    long_federated = build(
        activities=[activity("deporte_federado", date(2024, 1, 1), CALCULATION_DATE)]
    )
    long_subcommission = build(
        activities=[activity("subcomision", date(2024, 1, 1), CALCULATION_DATE)]
    )

    # La vigencia toca 13 meses calendario (oct 2025 a oct 2026): se cuentan 12.
    assert long_federated.activity_months["deporte_federado"] == 12
    assert long_federated.activity_points == 120
    assert long_subcommission.activity_points == 180


@pytest.mark.parametrize(
    ("start", "expected"),
    [(date(2025, 10, 1), 12), (date(2025, 11, 1), 12), (date(2025, 12, 1), 11)],
)
def test_months_below_the_cap_are_not_rounded_up(start: date, expected: int) -> None:
    inputs = build(activities=[activity("deporte_federado", start, CALCULATION_DATE)])

    assert inputs.activity_months["deporte_federado"] == expected


def test_a_month_counts_in_full_even_if_the_activity_covers_part_of_it() -> None:
    two_days = build(
        activities=[activity("deporte_federado", date(2026, 3, 31), date(2026, 4, 1))]
    )
    one_day = build(
        activities=[activity("subcomision", date(2026, 5, 15), date(2026, 5, 15))]
    )

    assert two_days.activity_months["deporte_federado"] == 2
    assert two_days.activity_points == 20
    assert one_day.activity_points == 15


def test_the_month_of_the_calculation_date_counts_in_full() -> None:
    inputs = build(
        activities=[
            activity("deporte_federado", date(2026, 10, 28), date(2026, 10, 29))
        ]
    )

    assert inputs.activity_months["deporte_federado"] == 1


def test_months_are_clipped_to_the_validity_period() -> None:
    inputs = build(
        activities=[activity("deporte_federado", date(2025, 1, 1), date(2025, 11, 15))]
    )

    # Dentro de la vigencia quedan oct 2025 (desde el 29) y nov 2025.
    assert inputs.activity_months["deporte_federado"] == 2


def test_months_cross_the_year_boundary() -> None:
    inputs = build(
        activities=[activity("subcomision", date(2025, 12, 15), date(2026, 2, 10))]
    )

    assert inputs.activity_months["subcomision"] == 3


def test_overlapping_records_of_the_same_activity_count_each_month_once() -> None:
    inputs = build(
        activities=[
            activity("deporte_federado", date(2026, 1, 1), date(2026, 3, 31)),
            activity("deporte_federado", date(2026, 3, 1), date(2026, 5, 31)),
        ]
    )

    assert inputs.activity_months["deporte_federado"] == 5


def test_disjoint_records_of_the_same_activity_add_up() -> None:
    inputs = build(
        activities=[
            activity("deporte_federado", date(2026, 1, 1), date(2026, 1, 31)),
            activity("deporte_federado", date(2026, 6, 1), date(2026, 7, 31)),
        ]
    )

    assert inputs.activity_months["deporte_federado"] == 3


def test_the_same_month_counts_for_each_activity() -> None:
    inputs = build(
        activities=[
            activity("deporte_federado", date(2026, 6, 1), date(2026, 6, 30)),
            activity("subcomision", date(2026, 6, 1), date(2026, 6, 30)),
        ]
    )

    assert inputs.activity_months == {"deporte_federado": 1, "subcomision": 1}
    assert inputs.activity_points == 25


def test_an_activity_that_starts_after_the_calculation_date_is_ignored() -> None:
    inputs = build(
        activities=[activity("subcomision", date(2026, 11, 1), date(2026, 12, 31))]
    )

    assert inputs.activity_points == 0


# --- Combinación ---------------------------------------------------------------------------


def test_an_assembly_of_40_and_three_federated_months_give_70() -> None:
    inputs = build(
        events=[event("ASAMBLEA", date(2026, 9, 10), 40)],
        activities=[activity("deporte_federado", date(2026, 5, 1), date(2026, 7, 31))],
    )

    assert inputs.points == 70


def test_no_participation_gives_zero_points() -> None:
    inputs = build()

    assert inputs.points == 0
    assert inputs.events == ()
    assert inputs.window_start == WINDOW_START


# --- Validación y forma serializable -------------------------------------------------------


def test_unknown_activity_kind_is_rejected() -> None:
    with pytest.raises(ValueError):
        ActivityRecord(kind="natacion", start=date(2026, 1, 1), end=date(2026, 1, 31))


def test_activity_ending_before_it_starts_is_rejected() -> None:
    with pytest.raises(ValueError):
        ActivityRecord(kind="subcomision", start=date(2026, 2, 1), end=date(2026, 1, 1))


@pytest.mark.parametrize("points", [0, -5])
def test_event_without_positive_points_is_rejected(points: int) -> None:
    with pytest.raises(ValueError):
        InstitutionalEvent(event_id="X", day=date(2026, 1, 1), points=points)


def test_as_dict_is_json_serializable_with_the_documented_shape() -> None:
    inputs = build(
        events=[event("ASAMBLEA", date(2026, 9, 10), 40)],
        activities=[activity("deporte_federado", date(2026, 5, 1), date(2026, 7, 31))],
    )

    assert json.loads(json.dumps(inputs.as_dict())) == {
        "window_start": "2025-10-29",
        "events": [{"event_id": "ASAMBLEA", "points": 40}],
        "event_points": 40,
        "activity_months": {"deporte_federado": 3, "subcomision": 0},
        "activity_points": 30,
        "points": 70,
    }
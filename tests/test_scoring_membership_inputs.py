"""HU-25, Ciclo 3c: antigüedad, edad y alta (módulo puro, sin base de datos)."""

import json
from datetime import date

import pytest

from app.scoring.membership_inputs import (
    MembershipInputs,
    build_membership_inputs,
    completed_years,
    days_between_previous_baja_and_alta,
)

CALCULATION_DATE = date(2026, 10, 29)


def build(
    *,
    birth_date: date = date(1980, 1, 1),
    alta: date = date(2015, 3, 1),
    previous_baja: date | None = None,
    calculation_date: date = CALCULATION_DATE,
) -> MembershipInputs:
    return build_membership_inputs(
        birth_date=birth_date,
        alta=alta,
        previous_baja=previous_baja,
        calculation_date=calculation_date,
    )


# --- Años cumplidos ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("since", "until", "expected"),
    [
        (date(1980, 1, 1), date(2026, 10, 29), 46),
        (date(1980, 10, 29), date(2026, 10, 29), 46),  # cumple años ese día
        (date(1980, 10, 30), date(2026, 10, 29), 45),  # cumple al día siguiente
        (date(2000, 2, 29), date(2026, 2, 28), 25),  # año no bisiesto: todavía no
        (date(2000, 2, 29), date(2026, 3, 1), 26),
        (date(2026, 10, 29), date(2026, 10, 29), 0),
        (date(2027, 1, 1), date(2026, 10, 29), 0),  # fecha futura: nunca negativo
    ],
)
def test_completed_years(since: date, until: date, expected: int) -> None:
    assert completed_years(since, until) == expected


# --- Días entre la baja previa y el alta ---------------------------------------------------


@pytest.mark.parametrize(
    ("previous_baja", "alta", "expected"),
    [
        (None, date(2026, 10, 19), None),
        (date(2026, 7, 11), date(2026, 10, 19), 100),
        (date(2025, 9, 14), date(2026, 10, 19), 400),
        (date(2026, 10, 19), date(2026, 10, 19), 0),
        (date(2025, 10, 19), date(2026, 10, 19), 365),
        (
            date(2026, 12, 1),
            date(2026, 10, 19),
            0,
        ),  # baja posterior al alta: dato incoherente
    ],
)
def test_days_between_previous_baja_and_alta(
    previous_baja: date | None, alta: date, expected: int | None
) -> None:
    assert days_between_previous_baja_and_alta(previous_baja, alta) == expected


# --- Antigüedad ----------------------------------------------------------------------------


def test_seniority_counts_from_the_alta_date() -> None:
    inputs = build(alta=date(2016, 10, 29))

    assert inputs.seniority_start == date(2016, 10, 29)
    assert inputs.seniority_years == 10


def test_an_alta_after_a_previous_baja_restarts_seniority_at_the_alta() -> None:
    # Volvió en 2022: lo anterior a la baja de 2021 no cuenta.
    inputs = build(alta=date(2022, 5, 10), previous_baja=date(2021, 1, 1))

    assert inputs.seniority_start == date(2022, 5, 10)
    assert inputs.seniority_years == 4
    assert inputs.days_between_previous_baja_and_alta == 494


def test_a_previous_baja_after_the_alta_restarts_seniority_at_the_baja() -> None:
    inputs = build(alta=date(2010, 1, 1), previous_baja=date(2020, 6, 1))

    assert inputs.seniority_start == date(2020, 6, 1)
    assert inputs.seniority_years == 6
    assert inputs.days_between_previous_baja_and_alta == 0


def test_a_future_alta_gives_zero_seniority_and_zero_days() -> None:
    inputs = build(alta=date(2027, 1, 1))

    assert inputs.seniority_years == 0
    assert inputs.days_since_alta == 0


# --- Edad y alta ---------------------------------------------------------------------------


def test_age_in_completed_years_at_the_calculation_date() -> None:
    assert build(birth_date=date(1980, 10, 29)).age_years == 46
    assert build(birth_date=date(1980, 10, 30)).age_years == 45


def test_new_member_bonus_from_alta_date() -> None:
    # `t` se cuenta desde el alta (no desde la baja ni desde la antigüedad).
    inputs = build(alta=date(2026, 10, 19), previous_baja=date(2020, 1, 1))

    assert inputs.days_since_alta == 10
    assert inputs.days_between_previous_baja_and_alta == 2483


# --- Forma serializable --------------------------------------------------------------------


def test_as_dict_is_json_serializable_with_the_documented_shape() -> None:
    inputs = build()

    assert json.loads(json.dumps(inputs.as_dict())) == {
        "birth_date": "1980-01-01",
        "seniority_start": "2015-03-01",
        "seniority_years": 11,
        "age_years": 46,
        "days_since_alta": 4260,
        "days_between_previous_baja_and_alta": None,
    }
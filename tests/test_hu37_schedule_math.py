"""HU-37: reglas puras del cronograma de oleadas (período, horas de inicio y estados)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.config import Settings
from app.schemas.wave_schedule import GenerateScheduleIn
from app.scoring.wave_schedule import validate_period

SECOND = timedelta(seconds=1)
MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)

# Ciclo 0: el mínimo entre oleadas es un setting (cross-cutting sección 8).


def test_the_min_step_setting_defaults_to_5_minutes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WAVE_MIN_STEP_MINUTES", raising=False)

    assert Settings(_env_file=None).wave_min_step_minutes == 5  # type: ignore[call-arg]


def test_the_min_step_setting_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WAVE_MIN_STEP_MINUTES", "10")

    assert Settings(_env_file=None).wave_min_step_minutes == 10  # type: ignore[call-arg]


@pytest.mark.parametrize("minutes", [0, -5])
def test_the_min_step_setting_must_be_positive(minutes: int) -> None:
    with pytest.raises(ValueError):
        Settings(wave_min_step_minutes=minutes)


# Ciclo 2: validación del período (escenario 2, FR-005). Reloj y partido de referencia.

NOW = datetime(2030, 3, 1, 12, 0, tzinfo=UTC)
KICKOFF = NOW + 10 * DAY


def violation_code(
    opening: datetime,
    closing: datetime,
    *,
    waves: int = 5,
    event_start: datetime = KICKOFF,
    now: datetime = NOW,
    min_step_minutes: int = 5,
) -> str | None:
    violation = validate_period(
        opening=opening,
        closing=closing,
        event_start=event_start,
        waves=waves,
        now=now,
        min_step_minutes=min_step_minutes,
    )
    return violation.code if violation else None


def test_a_valid_period_has_no_violation() -> None:
    assert violation_code(NOW + 2 * DAY, NOW + 3 * DAY) is None


def test_an_opening_equal_to_now_is_rejected() -> None:
    assert violation_code(NOW, NOW + DAY) == "OPENING_NOT_IN_FUTURE"


def test_an_opening_one_second_after_now_is_accepted() -> None:
    assert violation_code(NOW + SECOND, NOW + DAY) is None


def test_a_closing_equal_to_the_opening_is_rejected() -> None:
    opening = NOW + 2 * DAY

    assert violation_code(opening, opening) == "CLOSING_NOT_AFTER_OPENING"


def test_a_closing_before_the_opening_is_rejected() -> None:
    assert violation_code(NOW + 3 * DAY, NOW + 2 * DAY) == "CLOSING_NOT_AFTER_OPENING"


def test_a_closing_equal_to_the_event_start_is_accepted() -> None:
    assert violation_code(NOW + 2 * DAY, KICKOFF) is None


def test_a_closing_one_second_after_the_event_start_is_rejected() -> None:
    assert (
        violation_code(NOW + 2 * DAY, KICKOFF + SECOND) == "CLOSING_AFTER_EVENT_START"
    )


def test_a_step_of_exactly_the_minimum_is_accepted() -> None:
    opening = NOW + 2 * DAY

    assert violation_code(opening, opening + 25 * MINUTE) is None


def test_a_step_one_second_short_is_rejected() -> None:
    opening = NOW + 2 * DAY

    assert (
        violation_code(opening, opening + 25 * MINUTE - SECOND) == "WAVE_STEP_TOO_SHORT"
    )


def test_the_minimum_period_scales_with_the_number_of_waves() -> None:
    opening = NOW + 2 * DAY

    assert violation_code(opening, opening + 15 * MINUTE, waves=3) is None
    assert violation_code(opening, opening + 15 * MINUTE, waves=4) == (
        "WAVE_STEP_TOO_SHORT"
    )


def test_the_minimum_step_comes_from_the_argument() -> None:
    opening = NOW + 2 * DAY

    assert violation_code(opening, opening + HOUR, min_step_minutes=12) is None
    assert violation_code(opening, opening + HOUR, min_step_minutes=13) == (
        "WAVE_STEP_TOO_SHORT"
    )


def test_only_the_first_failing_rule_is_reported() -> None:
    # La apertura ya pasó y además el cierre es anterior: se informa la apertura.
    assert violation_code(NOW - DAY, NOW - 2 * DAY) == "OPENING_NOT_IN_FUTURE"
    # El cierre es posterior al partido y además el paso es corto: se informa el cierre.
    assert (
        violation_code(KICKOFF - MINUTE, KICKOFF + MINUTE)
        == "CLOSING_AFTER_EVENT_START"
    )


def test_the_step_message_states_the_minimum_and_the_minimum_period() -> None:
    opening = NOW + 2 * DAY

    violation = validate_period(
        opening=opening,
        closing=opening + 10 * MINUTE,
        event_start=KICKOFF,
        waves=5,
        now=NOW,
        min_step_minutes=5,
    )

    assert violation is not None
    assert violation.message == (
        "Entre oleadas tiene que haber al menos 5 minutos: con 5 oleadas, "
        "el período tiene que durar al menos 25 minutos."
    )


def test_the_step_message_uses_singular_for_a_single_wave() -> None:
    opening = NOW + 2 * DAY

    violation = validate_period(
        opening=opening,
        closing=opening + MINUTE,
        event_start=KICKOFF,
        waves=1,
        now=NOW,
        min_step_minutes=5,
    )

    assert violation is not None
    assert "con 1 oleada," in violation.message


# Ciclo 2: zona horaria de las fechas que llegan a la API (decisión 9 del plan).


def test_dates_without_time_zone_are_read_in_buenos_aires() -> None:
    body = GenerateScheduleIn.model_validate(
        {"opening_at": "2030-03-01T20:00:00", "closing_at": "2030-03-01T23:30"}
    )

    assert body.opening_at == datetime(2030, 3, 1, 23, 0, tzinfo=UTC)
    assert body.closing_at == datetime(2030, 3, 2, 2, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2030-03-01T20:00:00-03:00", datetime(2030, 3, 1, 23, 0, tzinfo=UTC)),
        ("2030-03-01T23:00:00Z", datetime(2030, 3, 1, 23, 0, tzinfo=UTC)),
        ("2030-03-01T23:00:00+00:00", datetime(2030, 3, 1, 23, 0, tzinfo=UTC)),
    ],
)
def test_dates_with_time_zone_keep_their_instant(
    value: str, expected: datetime
) -> None:
    body = GenerateScheduleIn.model_validate(
        {"opening_at": value, "closing_at": "2030-03-02T00:00:00Z"}
    )

    assert body.opening_at == expected
    assert body.opening_at.utcoffset() == timedelta(0)

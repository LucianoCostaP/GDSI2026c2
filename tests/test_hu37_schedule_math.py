"""HU-37: reglas puras del cronograma de oleadas (período, horas de inicio y estados)."""

import pytest

from app.config import Settings

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

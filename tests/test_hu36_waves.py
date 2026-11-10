"""HU-36: cálculo de las olas por percentil (escenarios 2 a 4, casos borde, SC-001 y SC-002)."""

import pytest

from app.config import Settings
from app.scoring.waves import Wave, build_waves, wave_of


def sizes(ranked_total: int, step: int = 20) -> list[int]:
    return [w.socios for w in build_waves(ranked_total, step)]


def test_103_socios_give_the_sizes_of_sc_002() -> None:
    assert sizes(103) == [20, 21, 20, 21, 21]


def test_bands_cover_20_40_60_80_100_with_wave_1_holding_the_best_positions() -> None:
    waves = build_waves(103, 20)

    assert [(w.percentile_from, w.percentile_to) for w in waves] == [
        (0, 20),
        (20, 40),
        (40, 60),
        (60, 80),
        (80, 100),
    ]
    assert waves[0].position_from == 1
    assert waves[-1].position_to == 103


def test_five_socios_give_one_per_wave() -> None:
    assert sizes(5) == [1, 1, 1, 1, 1]


def test_empty_bands_in_the_middle_are_omitted_and_the_rest_renumbered() -> None:
    assert build_waves(3, 20) == [
        Wave(
            order=1,
            percentile_from=20,
            percentile_to=40,
            position_from=1,
            position_to=1,
        ),
        Wave(
            order=2,
            percentile_from=60,
            percentile_to=80,
            position_from=2,
            position_to=2,
        ),
        Wave(
            order=3,
            percentile_from=80,
            percentile_to=100,
            position_from=3,
            position_to=3,
        ),
    ]


def test_a_single_socio_falls_in_the_last_band() -> None:
    assert build_waves(1, 20) == [
        Wave(
            order=1,
            percentile_from=80,
            percentile_to=100,
            position_from=1,
            position_to=1,
        )
    ]


def test_the_step_is_configurable() -> None:
    assert sizes(100, 25) == [25, 25, 25, 25]


@pytest.mark.parametrize("step", [10, 20, 25])
@pytest.mark.parametrize("ranked_total", [1, 2, 3, 7, 10, 99, 103, 1000, 1234])
def test_every_position_belongs_to_exactly_one_wave_and_sizes_differ_by_one(
    ranked_total: int, step: int
) -> None:
    waves = build_waves(ranked_total, step)
    covered = [p for w in waves for p in range(w.position_from, w.position_to + 1)]

    assert covered == list(range(1, ranked_total + 1))
    assert [w.order for w in waves] == list(range(1, len(waves) + 1))
    if len(waves) == 100 // step:
        assert max(sizes(ranked_total, step)) - min(sizes(ranked_total, step)) <= 1


@pytest.mark.parametrize("step", [10, 20, 25])
@pytest.mark.parametrize("ranked_total", [1, 3, 7, 103, 1234])
def test_wave_of_matches_the_percentile_formula_of_scenario_3(
    ranked_total: int, step: int
) -> None:
    waves = build_waves(ranked_total, step)
    for position in range(1, ranked_total + 1):
        percentile = 100 * position / ranked_total
        band = next(
            k
            for k in range(1, 100 // step + 1)
            if (k - 1) * step < percentile <= k * step
        )
        order = wave_of(position, ranked_total, step)
        assert order is not None
        assert waves[order - 1].percentile_to == band * step


def test_wave_of_is_none_outside_the_ranking() -> None:
    assert wave_of(104, 103, 20) is None


@pytest.mark.parametrize("ranked_total", [0, -1])
def test_an_empty_ranking_has_no_waves(ranked_total: int) -> None:
    with pytest.raises(ValueError):
        build_waves(ranked_total, 20)


def test_the_step_setting_defaults_to_20(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WAVE_PERCENTILE_STEP", raising=False)

    assert Settings(_env_file=None).wave_percentile_step == 20  # type: ignore[call-arg]


def test_the_step_setting_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WAVE_PERCENTILE_STEP", "25")

    assert Settings(_env_file=None).wave_percentile_step == 25  # type: ignore[call-arg]


@pytest.mark.parametrize("step", [0, -20, 30, 101])
def test_the_step_setting_must_divide_100(step: int) -> None:
    with pytest.raises(ValueError):
        Settings(wave_percentile_step=step)

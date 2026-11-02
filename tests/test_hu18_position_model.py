"""HU-18, "Position model": cálculo puro de la posición estimada (`app/scoring/position.py`)."""

import uuid
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from app.scoring.position import (
    OtherOutcome,
    PositionRange,
    attendance_probability,
    club_rate,
    estimate_position,
    z_for_level,
)
from app.scoring.ranking_order import RankingCandidate, ranks_above

Z80 = z_for_level(Decimal("0.80"))


def test_the_club_rate_is_of_the_class_of_the_partido() -> None:
    history = [
        ({"A": 1, "B": 3}, {"A": 2, "B": 4}),
        ({"A": 0, "B": 1}, {"A": 2, "B": 4}),
    ]

    assert club_rate(history, "B") == Fraction(4, 8)
    assert club_rate(history, "A") == Fraction(1, 4)


def test_without_matches_of_the_class_the_rate_is_over_all_classes() -> None:
    history = [
        ({"A": 1, "C": 0}, {"A": 2, "C": 0}),
        ({"A": 2, "C": 0}, {"A": 2, "C": 0}),
    ]

    assert club_rate(history, "C") == Fraction(3, 4)


def test_without_any_counted_match_there_is_no_rate() -> None:
    assert club_rate([({"B": 0}, {"B": 0})], "B") is None


def test_the_probability_is_smoothed_towards_the_club_rate() -> None:
    # Un partido asistido de uno no da 100 %: (1 + 5·0,5) / (1 + 5) = 7/12.
    assert attendance_probability(1, 1, Fraction(1, 2), Decimal(5)) == Fraction(7, 12)
    # Sin historial, la del club.
    assert attendance_probability(0, 0, Fraction(3, 5), Decimal(5)) == Fraction(3, 5)


def test_z_of_the_default_range_level() -> None:
    assert round(Z80, 4) == 1.2816


@pytest.mark.parametrize("level", ["0", "1", "1.20"])
def test_an_invalid_range_level_fails(level: str) -> None:
    with pytest.raises(ValueError):
        z_for_level(Decimal(level))


def test_certain_socios_add_no_spread() -> None:
    always_above = OtherOutcome(Fraction(1, 3), True, True)
    always_below = OtherOutcome(Fraction(2, 3), False, False)

    position = estimate_position([always_above, always_above, always_below], 4, Z80)

    assert position == PositionRange(estimate=3, lower=3, upper=3)


def test_a_rival_above_only_if_attending_adds_its_probability_and_spread() -> None:
    # μ = 1 + 1/2, centro 2,5 → puesto 3 (redondeo hacia arriba en .5);
    # σ = 0,5, z·σ = 0,64 → rango [floor(1,86), ceil(3,14)] = [1, 4].
    others = [
        OtherOutcome(Fraction(1, 5), True, True),
        OtherOutcome(Fraction(1, 2), True, False),
    ]

    assert estimate_position(others, 10, Z80) == PositionRange(3, 1, 4)


def test_the_range_is_clipped_to_the_population() -> None:
    others = [OtherOutcome(Fraction(1, 2), True, False) for _ in range(4)]

    position = estimate_position(others, 5, z=10.0)

    assert position.lower == 1 and position.upper == 5


def test_ranks_above_uses_the_ranking_tiebreaks() -> None:
    def candidate(total: str, seniority: date, dni: str) -> RankingCandidate:
        return RankingCandidate(
            uuid.uuid4(), Decimal(total), seniority, date(1980, 1, 1), dni
        )

    older = candidate("50.00", date(2010, 1, 1), "30000000")
    newer = candidate("50.00", date(2015, 1, 1), "4000000")

    assert ranks_above(candidate("50.01", date(2020, 1, 1), "9"), older)
    assert ranks_above(older, newer) and not ranks_above(newer, older)
    assert not ranks_above(older, older)

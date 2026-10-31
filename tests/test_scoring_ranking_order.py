"""HU-25, Ciclo 4: desempates y posiciones únicas (módulo puro, sin base de datos)."""

import random
import uuid
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise

from app.scoring.ranking_order import RankingCandidate, assign_positions

TOTAL = Decimal("59.55")
SENIORITY = date(2010, 5, 1)
BIRTH = date(1970, 3, 3)


def candidate(
    dni: str,
    *,
    total: Decimal = TOTAL,
    seniority_start: date = SENIORITY,
    birth_date: date = BIRTH,
) -> RankingCandidate:
    return RankingCandidate(
        socio_id=uuid.uuid4(),
        total=total,
        seniority_start=seniority_start,
        birth_date=birth_date,
        dni=dni,
    )


def order_of(candidates: list[RankingCandidate]) -> list[str]:
    return [c.dni for _, c in assign_positions(candidates)]


# --- Desempates ----------------------------------------------------------------------------


def test_a_higher_total_goes_first_whatever_the_tiebreaks() -> None:
    low = candidate("1", total=Decimal("59.54"), seniority_start=date(1980, 1, 1))
    high = candidate("2", total=Decimal("59.55"), seniority_start=date(2020, 1, 1))

    assert order_of([low, high]) == ["2", "1"]


def test_tie_broken_by_seniority() -> None:
    newer = candidate("1", seniority_start=date(2015, 1, 1))
    oldest = candidate("2", seniority_start=date(2001, 6, 1))
    middle = candidate("3", seniority_start=date(2010, 9, 9))

    assert order_of([newer, oldest, middle]) == ["2", "3", "1"]


def test_seniority_compares_the_exact_date_not_the_completed_years() -> None:
    # Mismos años cumplidos a cualquier fecha de cálculo, distinto día de inicio.
    later_in_the_year = candidate("1", seniority_start=date(2010, 11, 30))
    earlier_in_the_year = candidate("2", seniority_start=date(2010, 1, 2))

    assert order_of([later_in_the_year, earlier_in_the_year]) == ["2", "1"]


def test_tie_broken_by_age_when_seniority_equal() -> None:
    younger = candidate("1", birth_date=date(1990, 1, 1))
    oldest = candidate("2", birth_date=date(1950, 7, 7))
    middle = candidate("3", birth_date=date(1970, 3, 3))

    assert order_of([younger, oldest, middle]) == ["2", "3", "1"]


def test_seniority_beats_age() -> None:
    more_senior_but_younger = candidate(
        "1", seniority_start=date(2001, 1, 1), birth_date=date(1990, 1, 1)
    )
    less_senior_but_older = candidate(
        "2", seniority_start=date(2005, 1, 1), birth_date=date(1940, 1, 1)
    )

    assert order_of([less_senior_but_older, more_senior_but_younger]) == ["1", "2"]


def test_tie_broken_by_lower_dni_when_all_equal() -> None:
    assert order_of(
        [candidate("30000003"), candidate("10000001"), candidate("20000002")]
    ) == [
        "10000001",
        "20000002",
        "30000003",
    ]


def test_dni_compares_as_a_number_not_as_text() -> None:
    assert order_of([candidate("30000001"), candidate("4000000")]) == [
        "4000000",
        "30000001",
    ]


def test_dni_ignores_dots_and_spaces_and_keeps_numeric_ones_first() -> None:
    dotted = candidate("5.000.000")
    plain = candidate("12000000")
    spaced = candidate("6 000 000")
    foreign = candidate("AB123456")

    assert order_of([foreign, plain, spaced, dotted]) == [
        "5.000.000",
        "6 000 000",
        "12000000",
        "AB123456",
    ]


def test_dnis_that_read_the_same_number_are_still_ordered_deterministically() -> None:
    assert order_of([candidate("012"), candidate("12")]) == order_of(
        [candidate("12"), candidate("012")]
    )


# --- Total a dos decimales -----------------------------------------------------------------


def test_order_uses_two_decimal_total() -> None:
    # 59,554 y 59,549 se muestran los dos como 59,55: empatan y decide la antigüedad.
    senior = candidate("2", total=Decimal("59.549"), seniority_start=date(2001, 1, 1))
    junior = candidate("1", total=Decimal("59.554"), seniority_start=date(2012, 1, 1))

    assert order_of([junior, senior]) == ["2", "1"]


def test_totals_that_differ_only_in_trailing_zeros_tie() -> None:
    senior = candidate("2", total=Decimal("59.5"), seniority_start=date(2001, 1, 1))
    junior = candidate("1", total=Decimal("59.50"), seniority_start=date(2012, 1, 1))

    assert order_of([junior, senior]) == ["2", "1"]


def test_a_centesimal_difference_is_enough_to_break_the_order() -> None:
    assert order_of(
        [candidate("1", total=Decimal("59.54")), candidate("2", total=Decimal("59.55"))]
    ) == ["2", "1"]


# --- Posiciones ----------------------------------------------------------------------------


def test_positions_unique_and_consecutive() -> None:
    candidates = [candidate(str(n)) for n in range(1, 8)]

    positions = [position for position, _ in assign_positions(candidates)]

    assert positions == [1, 2, 3, 4, 5, 6, 7]


def test_no_candidates_gives_no_positions() -> None:
    assert assign_positions([]) == []


def test_a_single_candidate_gets_position_one() -> None:
    [(position, _)] = assign_positions([candidate("1")])

    assert position == 1


# --- Propiedades con datos aleatorios ------------------------------------------------------


def random_candidates(rng: random.Random, size: int) -> list[RankingCandidate]:
    dnis = rng.sample(range(1_000_000, 60_000_000), size)
    return [
        candidate(
            str(dni),
            # Pocos valores posibles para que haya muchísimos empates.
            total=Decimal(rng.choice(["10.00", "10.01", "55.55", "100.00"])),
            seniority_start=date(2000, 1, 1) + timedelta(days=rng.randrange(3)),
            birth_date=date(1950, 1, 1) + timedelta(days=rng.randrange(3)),
        )
        for dni in dnis
    ]


def test_positions_are_always_unique_and_consecutive_with_random_data() -> None:
    for seed in range(200):
        rng = random.Random(seed)
        candidates = random_candidates(rng, rng.randrange(1, 60))

        ranked = assign_positions(candidates)

        assert [p for p, _ in ranked] == list(range(1, len(candidates) + 1))
        assert {c.socio_id for _, c in ranked} == {c.socio_id for c in candidates}


def test_the_order_does_not_depend_on_the_input_order() -> None:
    for seed in range(100):
        rng = random.Random(seed)
        candidates = random_candidates(rng, 40)
        shuffled = candidates[:]
        rng.shuffle(shuffled)

        assert order_of(candidates) == order_of(shuffled)


def test_the_order_respects_every_criterion_with_random_data() -> None:
    for seed in range(100):
        rng = random.Random(seed)
        ranked = [c for _, c in assign_positions(random_candidates(rng, 40))]

        for first, second in pairwise(ranked):
            assert first.total >= second.total
            if first.total == second.total:
                assert first.seniority_start <= second.seniority_start
                if first.seniority_start == second.seniority_start:
                    assert first.birth_date <= second.birth_date
                    if first.birth_date == second.birth_date:
                        assert int(first.dni) < int(second.dni)

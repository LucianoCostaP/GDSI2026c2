"""HU-29, escenario 12: media, mediana, desvío y percentiles de los totales.

"Given a simulation result, When it is shown, Then it includes, for both situations, the mean,
the median, the standard deviation and the 10th and 90th percentiles of the totals (definitions
in "Calculation definitions"), and their differences." Contrato:
`docs/contrato-api-simulacion-reglas.md` §5.2 y §5.4.
"""

import math
import statistics
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, User
from app.scoring.distribution import Summary, median, percentile, summary
from app.scoring.formatting import decimal_fixed
from tests.conftest import Outbox
from tests.hu25_helpers import (
    DEFAULTS,
    adjust_rules,
    entries_of,
    headers_for,
    publish_rules,
)
from tests.hu29_helpers import CHANGED, SIMULATOR, make_varied_club, run_ranking

STATS = ("mean", "median", "std_dev", "p10", "p90")


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


@pytest.fixture
def ranking(db: Session, admin: User, boca: dict[str, str]) -> Ranking:
    make_varied_club(db)
    return run_ranking(db, admin)


def simulate(
    client: TestClient, headers: dict[str, str], values: dict[str, Any]
) -> Any:
    response = client.post(SIMULATOR, json={"values": values}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def reference(totals: list[Decimal]) -> dict[str, Decimal]:
    """Las definiciones del spec con la biblioteca estándar, como cálculo independiente."""
    ordered = sorted(totals)
    n = len(ordered)
    return {
        "mean": statistics.mean(ordered),
        "median": statistics.median(ordered),
        "std_dev": statistics.pstdev(ordered),
        "p10": ordered[math.ceil(10 * n / 100) - 1],
        "p90": ordered[math.ceil(90 * n / 100) - 1],
    }


def shown(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) + 0)


# --- Aceptación ----------------------------------------------------------------------------


def test_the_result_has_the_statistics_of_the_ranking_and_of_the_simulation(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
) -> None:
    body = simulate(client, boca, CHANGED)
    # La simulación da lo mismo que un cálculo real de HU-25 con esas reglas (escenario 8).
    adjust_rules(client, boca, 1, **CHANGED)
    official = run_ranking(db, admin)

    before = reference([e.total for e in entries_of(db, ranking)])
    after = reference([e.total for e in entries_of(db, official)])
    assert body["summary"]["before"] == {key: shown(before[key]) for key in STATS}
    assert body["summary"]["after"] == {key: shown(after[key]) for key in STATS}
    # Las reglas nuevas cambian los totales: si no, el test no distinguiría las columnas.
    assert body["summary"]["before"] != body["summary"]["after"]


def test_the_differences_are_simulation_minus_ranking_from_the_exact_values(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
) -> None:
    body = simulate(client, boca, CHANGED)
    adjust_rules(client, boca, 1, **CHANGED)
    official = run_ranking(db, admin)

    before = reference([e.total for e in entries_of(db, ranking)])
    after = reference([e.total for e in entries_of(db, official)])
    assert body["summary"]["difference"] == {
        key: shown(after[key] - before[key]) for key in STATS
    }


def test_every_statistic_is_shown_with_two_decimals(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, CHANGED)

    for column in ("before", "after", "difference"):
        for value in body["summary"][column].values():
            assert Decimal(value).as_tuple().exponent == -2, (column, value)


def test_with_the_values_of_the_ranking_the_statistics_are_equal(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, DEFAULTS)

    assert body["status"] == "no_changes"
    assert body["summary"]["before"] == body["summary"]["after"]
    assert body["summary"]["difference"] == dict.fromkeys(STATS, "0.00")


# --- Unitarias: definiciones ---------------------------------------------------------------


def totals(*values: str) -> list[Decimal]:
    return [Decimal(v) for v in values]


def test_the_median_of_an_odd_count_is_the_middle_total() -> None:
    assert median(sorted(totals("50", "10", "30"))) == Decimal(30)


def test_the_median_of_an_even_count_is_the_mean_of_the_two_middle_ones() -> None:
    assert median(sorted(totals("10", "20.01", "30", "90"))) == Decimal("25.005")


@pytest.mark.parametrize(
    ("n", "p10_rank", "p90_rank"),
    [
        (1, 1, 1),
        (2, 1, 2),
        (9, 1, 9),
        (10, 1, 9),
        (11, 2, 10),
        (20, 2, 18),
        (21, 3, 19),
    ],
)
def test_percentiles_use_the_nearest_rank(n: int, p10_rank: int, p90_rank: int) -> None:
    # El total de la posición k (en orden ascendente) es k: así se lee el rango.
    ordered = [Decimal(k) for k in range(1, n + 1)]

    assert percentile(ordered, 10) == p10_rank
    assert percentile(ordered, 90) == p90_rank


def test_the_standard_deviation_is_the_population_one() -> None:
    # Media 5; desvíos 3, 1, 1, 1, 0, 0, 2, 4: varianza 32/8 = 4 (con N − 1 sería 4,57).
    stats = summary(totals("2", "4", "4", "4", "5", "5", "7", "9"))

    assert stats.mean == 5
    assert stats.std_dev == 2


def test_a_single_socio_has_no_dispersion() -> None:
    assert summary(totals("59.55")) == Summary(
        mean=Decimal("59.55"),
        median=Decimal("59.55"),
        std_dev=Decimal(0),
        p10=Decimal("59.55"),
        p90=Decimal("59.55"),
    )


def test_the_statistics_match_the_standard_library() -> None:
    values = totals("0", "12.34", "12.34", "45.10", "59.55", "66.75", "99.99", "100")

    stats = summary(values)

    expected = reference(values)
    assert stats.mean == expected["mean"]
    assert stats.median == expected["median"]
    assert abs(stats.std_dev - expected["std_dev"]) < Decimal("1e-20")
    assert (stats.p10, stats.p90) == (expected["p10"], expected["p90"])


def test_the_difference_uses_the_exact_values() -> None:
    before = summary(totals("10", "10", "10.01"))
    after = summary(totals("10", "10.01", "10.01"))

    difference = after.minus(before)

    # 10.0066… − 10.0033… = 0.0033…: redondeado da 0.00, no 10.01 − 10.00 = 0.01.
    assert decimal_fixed(before.mean, 2) == "10.00"
    assert decimal_fixed(after.mean, 2) == "10.01"
    assert decimal_fixed(difference.mean, 2) == "0.00"
    assert difference.median == Decimal("0.01")


def test_the_statistics_need_at_least_one_total() -> None:
    with pytest.raises(ValueError):
        summary([])


def test_the_totals_must_have_two_decimals() -> None:
    with pytest.raises(ValueError):
        summary(totals("10.005"))


# --- Unitarias: cómo se muestran -----------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("46.9", "46.90"),
        ("14.224", "14.22"),
        ("14.225", "14.23"),
        ("-0.925", "-0.93"),
        ("-0.004", "0.00"),
        ("0", "0.00"),
    ],
)
def test_statistics_are_rounded_half_up_to_two_decimals(value: str, text: str) -> None:
    assert decimal_fixed(Decimal(value), 2) == text

"""HU-29, escenario 11: histograma de los totales en 20 bins.

"Given a simulation result, When it is shown, Then it includes, for the ranking and for the
simulation, a histogram of the totals in 20 fixed bins of 5 points (`[0,5)`, `[5,10)`, …
`[90,95)`, and `[95,100]`, so a total of exactly 100 falls in the last one), with the number of
Socios of each bin." Contrato: `docs/contrato-api-simulacion-reglas.md` §5.2 y §5.4.
"""

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, User
from app.scoring.distribution import BINS, bin_index, histogram
from tests.conftest import Outbox
from tests.hu25_helpers import (
    DEFAULTS,
    adjust_rules,
    entries_of,
    headers_for,
    publish_rules,
)
from tests.hu29_helpers import CHANGED, SIMULATOR, make_varied_club, run_ranking


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


def counted(totals: list[Decimal]) -> list[int]:
    """El histograma esperado, contado a mano con los límites de cada bin."""
    return [
        sum(
            1
            for total in totals
            if low <= total < low + 5 or (low == 95 and total == 100)
        )
        for low in range(0, 100, 5)
    ]


EXPECTED_BINS = [
    {"label": f"[{low},{low + 5})", "lower": str(low), "upper": str(low + 5)}
    for low in range(0, 95, 5)
] + [{"label": "[95,100]", "lower": "95", "upper": "100"}]


# --- Aceptación ----------------------------------------------------------------------------


def test_the_result_has_the_20_fixed_bins_in_order(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, CHANGED)

    assert [
        {key: b[key] for key in ("label", "lower", "upper")} for b in body["histogram"]
    ] == EXPECTED_BINS


def test_each_bin_counts_the_socios_of_the_ranking_and_of_the_simulation(
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

    before = counted([e.total for e in entries_of(db, ranking)])
    after = counted([e.total for e in entries_of(db, official)])
    assert [b["before"] for b in body["histogram"]] == before
    assert [b["after"] for b in body["histogram"]] == after
    # Las reglas nuevas cambian la distribución: si no, el test no distinguiría las columnas.
    assert before != after


def test_the_counts_of_each_column_add_up_to_the_population(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, CHANGED)

    assert sum(b["before"] for b in body["histogram"]) == ranking.population_size == 7
    assert sum(b["after"] for b in body["histogram"]) == ranking.population_size


def test_with_the_values_of_the_ranking_both_histograms_are_equal(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, DEFAULTS)

    assert body["status"] == "no_changes"
    assert len(body["histogram"]) == 20
    assert all(b["before"] == b["after"] for b in body["histogram"])


# --- Unitarias -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("total", "index"),
    [
        ("0", 0),
        ("0.00", 0),
        ("4.99", 0),
        ("5", 1),
        ("5.00", 1),
        ("49.99", 9),
        ("50", 10),
        ("94.99", 18),
        ("95", 19),
        ("99.99", 19),
        ("100", 19),
        ("100.00", 19),
    ],
)
def test_each_total_falls_in_its_bin(total: str, index: int) -> None:
    assert bin_index(Decimal(total)) == index


@pytest.mark.parametrize("total", ["-0.01", "100.01"])
def test_a_total_outside_the_scale_is_an_error(total: str) -> None:
    with pytest.raises(ValueError):
        bin_index(Decimal(total))


def test_the_histogram_counts_every_total_once() -> None:
    totals = [Decimal(t) for t in ("0", "4.99", "5", "5", "59.55", "95", "100", "100")]

    counts = histogram(totals)

    assert len(counts) == 20
    assert sum(counts) == len(totals)
    assert counts[0] == 2 and counts[1] == 2 and counts[11] == 1 and counts[19] == 3


def test_the_last_bin_is_closed_and_the_rest_half_open() -> None:
    assert [b.label for b in BINS[:2]] == ["[0,5)", "[5,10)"]
    assert BINS[18].label == "[90,95)"
    assert BINS[19].label == "[95,100]"
    assert (BINS[0].lower, BINS[-1].upper) == (0, 100)

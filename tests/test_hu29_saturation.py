"""HU-29, escenario 14: tope, ajuste por tope y empates.

"Given a simulation result, When it is shown, Then for both situations it shows the number of
Socios whose total is 100.00, the number of Socios that need a cap adjustment (their components
add more than 100), the number of Socios tied with at least one other Socio at two decimals and
the size of the largest tie." Contrato: `docs/contrato-api-simulacion-reglas.md` §5.2 y §5.4.
"""

from collections import Counter
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, RankingEntry, User
from app.scoring.distribution import Saturation, saturation
from tests.conftest import Outbox
from tests.hu25_helpers import (
    DEFAULTS,
    adjust_rules,
    entries_of,
    headers_for,
    publish_rules,
)
from tests.hu29_helpers import (
    SIMULATOR,
    TO_THE_CAP,
    make_saturation_club,
    run_ranking,
)


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


@pytest.fixture
def ranking(db: Session, admin: User, boca: dict[str, str]) -> Ranking:
    make_saturation_club(db)
    return run_ranking(db, admin)


def simulate(
    client: TestClient, headers: dict[str, str], values: dict[str, Any]
) -> Any:
    response = client.post(SIMULATOR, json={"values": values}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def counted(entries: list[RankingEntry]) -> dict[str, int]:
    """Los conteos esperados, hechos a mano sobre las entradas de un ranking real."""
    groups = [n for n in Counter(e.total for e in entries).values() if n > 1]
    return {
        "at_cap": sum(1 for e in entries if e.total == Decimal("100.00")),
        "needs_cap_adjustment": sum(1 for e in entries if e.cap_adjustment < 0),
        "tied": sum(groups),
        "largest_tie": max(groups, default=0),
    }


# --- Aceptación ----------------------------------------------------------------------------


def test_the_result_has_the_saturation_of_the_ranking_and_of_the_simulation(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
) -> None:
    body = simulate(client, boca, TO_THE_CAP)
    # La simulación da lo mismo que un cálculo real de HU-25 con esas reglas (escenario 8).
    adjust_rules(client, boca, 1, **TO_THE_CAP)
    official = run_ranking(db, admin)

    assert body["saturation"] == {
        "before": counted(entries_of(db, ranking)),
        "after": counted(entries_of(db, official)),
    }


def test_the_counts_are_the_expected_ones(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, TO_THE_CAP)

    # Hoy nadie llega a 100; con estos valores el socio estrella pasa de 100 y se ajusta.
    assert body["saturation"]["before"] == {
        "at_cap": 0,
        "needs_cap_adjustment": 0,
        "tied": 5,
        "largest_tie": 3,
    }
    assert body["saturation"]["after"]["at_cap"] == 1
    assert body["saturation"]["after"]["needs_cap_adjustment"] == 1
    assert body["saturation"]["after"]["largest_tie"] == 3


def test_with_the_values_of_the_ranking_both_situations_are_equal(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, DEFAULTS)

    assert body["status"] == "no_changes"
    assert body["saturation"]["before"] == body["saturation"]["after"]


# --- Unitarias -----------------------------------------------------------------------------


def amounts(*values: str) -> list[Decimal]:
    return [Decimal(v) for v in values]


def test_only_a_total_of_exactly_100_is_at_the_cap() -> None:
    totals = amounts("100.00", "100", "99.99", "0")

    assert saturation(totals, amounts("0", "0", "0", "0")).at_cap == 2


def test_a_cap_adjustment_is_counted_only_when_negative() -> None:
    # Llegar justo a 100 no necesita ajuste: el ajuste aparece solo si la suma pasaba de 100.
    counts = saturation(amounts("100", "100", "50"), amounts("-0.01", "0.00", "0"))

    assert counts.needs_cap_adjustment == 1
    assert counts.at_cap == 2


def test_ties_count_every_socio_of_every_tied_group() -> None:
    totals = amounts("10", "10.00", "10", "20", "20", "30", "40")

    counts = saturation(totals, [Decimal(0)] * len(totals))

    assert (counts.tied, counts.largest_tie) == (5, 3)


def test_without_ties_the_largest_tie_is_0() -> None:
    assert saturation(amounts("10", "20", "30"), amounts("0", "0", "0")) == Saturation(
        at_cap=0, needs_cap_adjustment=0, tied=0, largest_tie=0
    )


def test_ties_are_compared_at_two_decimals_as_stored() -> None:
    # 10.01 y 10.00 son totales distintos: no empatan.
    counts = saturation(amounts("10.01", "10.00"), amounts("0", "0"))

    assert counts.tied == 0


def test_each_total_needs_its_cap_adjustment() -> None:
    with pytest.raises(ValueError):
        saturation(amounts("10", "20"), amounts("0"))

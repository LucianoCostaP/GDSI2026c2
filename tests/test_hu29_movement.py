"""HU-29, escenario 13: movimiento de posiciones frente al ranking.

"Given a simulation result, When it is shown, Then it includes how many Socios go up, how many
go down and how many keep their position versus the ranking, the mean absolute change of
position, and how many go up and how many go down in a relevant way (definitions in
"Calculation definitions"). Unchanged Socios count in neither "up" nor "down"."
Contrato: `docs/contrato-api-simulacion-reglas.md` §5.2 y §5.4.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, User
from app.scoring.rules_simulation import (
    SimulatedEntry,
    StoredEntry,
    movement,
    relevant_threshold,
)
from app.services import rules_simulation_service
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


# --- Aceptación ----------------------------------------------------------------------------


def test_the_result_has_the_movement_against_the_ranking(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
) -> None:
    body = simulate(client, boca, CHANGED)
    # La simulación da lo mismo que un cálculo real de HU-25 con esas reglas (escenario 8).
    adjust_rules(client, boca, 1, **CHANGED)
    official = {e.socio_id: e.position for e in entries_of(db, run_ranking(db, admin))}

    changes = [e.position - official[e.socio_id] for e in entries_of(db, ranking)]
    mean_abs = Decimal(sum(abs(c) for c in changes)) / len(changes)
    # Con 7 socios, m = max(1, ceil(7/100)) = 1: todo cambio es relevante.
    assert body["movement"] == {
        "up": sum(1 for c in changes if c > 0),
        "down": sum(1 for c in changes if c < 0),
        "unchanged": sum(1 for c in changes if c == 0),
        "mean_abs_position_change": str(
            mean_abs.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        ),
        "relevant_threshold": 1,
        "relevant_up": sum(1 for c in changes if c >= 1),
        "relevant_down": sum(1 for c in changes if c <= -1),
    }
    # Las reglas nuevas mueven el ranking: si no, el test no probaría nada.
    assert body["movement"]["up"] > 0 and body["movement"]["down"] > 0


def test_up_down_and_unchanged_add_up_to_the_population(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    moved = simulate(client, boca, CHANGED)["movement"]

    assert moved["up"] + moved["down"] + moved["unchanged"] == 7
    assert moved["relevant_up"] <= moved["up"]
    assert moved["relevant_down"] <= moved["down"]


def test_with_the_values_of_the_ranking_nobody_moves(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    moved = simulate(client, boca, DEFAULTS)["movement"]

    assert moved["unchanged"] == 7
    assert (moved["up"], moved["down"]) == (0, 0)
    assert moved["mean_abs_position_change"] == "0.0"
    assert (moved["relevant_up"], moved["relevant_down"]) == (0, 0)


# --- Unitarias -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("population", "m"),
    [(1, 1), (7, 1), (99, 1), (100, 1), (101, 2), (200, 2), (201, 3), (10000, 100)],
)
def test_the_relevant_threshold_is_one_percent_of_the_ranking(
    population: int, m: int
) -> None:
    assert relevant_threshold(population) == m


def moved_by(changes: list[int]) -> tuple[list[StoredEntry], list[SimulatedEntry]]:
    """Socios con `cambio = posición del ranking − posición simulada` dado.

    Solo importan las posiciones; no hace falta que formen un ranking consistente.
    """
    start = 1000
    before = [
        StoredEntry(uuid.uuid4(), start + i, {}, Decimal(0), {})
        for i in range(len(changes))
    ]
    after = [
        SimulatedEntry(entry.socio_id, entry.position - change, {}, Decimal(0))
        for entry, change in zip(before, changes, strict=True)
    ]
    return before, after


def test_relevant_moves_need_at_least_m_positions() -> None:
    # 250 socios: m = 3. Cambios de ±3 o más son relevantes; ±1 y ±2, no.
    changes = [3, 4, 2, 1, -3, -10, -2, 0] + [0] * 242
    before, after = moved_by(changes)

    moved = movement(before, after)

    assert moved.relevant_threshold == 3
    assert (moved.up, moved.down, moved.unchanged) == (4, 3, 243)
    assert (moved.relevant_up, moved.relevant_down) == (2, 2)


def test_the_mean_absolute_change_is_exact() -> None:
    before, after = moved_by([1, -2, 0])

    moved = movement(before, after)

    assert moved.mean_abs_position_change == Decimal(1)


def test_the_mean_absolute_change_is_not_rounded_inside() -> None:
    before, after = moved_by([1, 0, 0])

    assert movement(before, after).mean_abs_position_change == Decimal(1) / 3


@pytest.mark.parametrize(
    ("changes", "text"),
    [([1, 0, 0, 0], "0.3"), ([1, 0, 0, 0, 0, 0, 0, 0], "0.1"), ([3, -2, 0, 0], "1.3")],
)
def test_the_mean_absolute_change_is_shown_with_one_decimal_half_up(
    client: TestClient,
    boca: dict[str, str],
    ranking: Ranking,
    monkeypatch: pytest.MonkeyPatch,
    changes: list[int],
    text: str,
) -> None:
    # 0.25 -> 0.3 y 0.125 -> 0.1; 1.25 -> 1.3.
    before, after = moved_by(changes)
    monkeypatch.setattr(
        rules_simulation_service, "movement", lambda *_: movement(before, after)
    )

    moved = simulate(client, boca, CHANGED)["movement"]

    assert moved["mean_abs_position_change"] == text


def test_an_empty_population_does_not_divide_by_zero() -> None:
    moved = movement([], [])

    assert moved.mean_abs_position_change == 0
    assert (moved.up, moved.down, moved.unchanged) == (0, 0, 0)

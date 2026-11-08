"""HU-29, escenario 20: un solo factor cambiado, o ninguno.

"Given only one factor changed (including only "other parameters"), When the result is shown,
Then no isolated simulation is run and the message `SINGLE_FACTOR` states that its effect is
the one of the total. Given no factor changed, Then scenario 9 applies."
Contrato: `docs/contrato-api-simulacion-reglas.md` §5.2 (`breakdown`), §5.4 y §6.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, User
from app.scoring import rules_simulation
from app.services import rules_simulation_service
from tests.conftest import Outbox
from tests.hu25_helpers import DEFAULTS, headers_for, publish_rules
from tests.hu29_helpers import (
    ISOLATED,
    SIMULATOR,
    SPREAD,
    make_saturation_club,
    run_ranking,
)

BREAKDOWN = f"{SIMULATOR}/breakdown"
SINGLE_FACTOR = (
    "Cambiaste un solo grupo de parámetros: su efecto es el del resultado total."
)
NO_CHANGES = (
    "Los valores son iguales a los del ranking: no hay diferencias para mostrar."
)
ONE_FACTOR = pytest.mark.parametrize(
    "values",
    [
        ISOLATED["pillar_weights"],
        {"w_a": "0.7", "w_t": "0.1"},
        ISOLATED["alpha_a"],
        ISOLATED["d_sat"],
        {"b_max": "20"},
        {"b_max": "20", "gamma": "0.9", "t_carencia": "180"},
    ],
    ids=[
        "pillar-weights",
        "two-weights",
        "alpha-a",
        "d-sat",
        "one-other",
        "many-other",
    ],
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


@pytest.fixture
def simulations(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Cuenta los recálculos completos del ranking que hace el servicio."""
    calls: list[int] = []
    original: Callable[..., Any] = rules_simulation.simulate_entries

    def counting(*args: Any) -> Any:
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(rules_simulation_service, "simulate_entries", counting)
    return calls


def simulate(
    client: TestClient, headers: dict[str, str], values: dict[str, Any]
) -> Any:
    response = client.post(SIMULATOR, json={"values": values}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def breakdown(
    client: TestClient, headers: dict[str, str], ranking_id: int, values: dict[str, Any]
) -> Any:
    response = client.post(
        BREAKDOWN, json={"ranking_id": ranking_id, "values": values}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- Aceptación: un solo factor ------------------------------------------------------------


@ONE_FACTOR
def test_with_a_single_factor_the_result_says_its_effect_is_the_total(
    client: TestClient,
    boca: dict[str, str],
    ranking: Ranking,
    values: dict[str, str],
) -> None:
    body = simulate(client, boca, {**DEFAULTS, **values})

    assert body["status"] == "changed"
    assert len(body["factors_changed"]) == 1
    assert body["breakdown"] == {
        "status": "single_factor",
        "code": "SINGLE_FACTOR",
        "message": SINGLE_FACTOR,
    }


@ONE_FACTOR
def test_with_a_single_factor_no_isolated_simulation_is_run(
    client: TestClient,
    boca: dict[str, str],
    ranking: Ranking,
    simulations: list[int],
    values: dict[str, str],
) -> None:
    body = breakdown(client, boca, ranking.id, {**DEFAULTS, **values})

    assert simulations == []
    assert body == {
        "ranking_id": ranking.id,
        "status": "single_factor",
        "code": "SINGLE_FACTOR",
        "message": SINGLE_FACTOR,
        "factors": [],
        "remainder": None,
        "non_additive_note": None,
    }


def test_the_main_result_runs_only_the_full_simulation(
    client: TestClient,
    boca: dict[str, str],
    ranking: Ranking,
    simulations: list[int],
) -> None:
    simulate(client, boca, {**DEFAULTS, **ISOLATED["d_sat"]})

    assert simulations == [1]


def test_with_two_factors_the_isolated_simulations_are_run(
    client: TestClient,
    boca: dict[str, str],
    ranking: Ranking,
    simulations: list[int],
) -> None:
    # Contraste: con los cuatro factores, la completa y una por cada uno de los tres aislables.
    body = breakdown(client, boca, ranking.id, SPREAD)

    assert body["status"] == "available"
    assert len(simulations) == 4


# --- Aceptación: ningún factor (escenario 9) ------------------------------------------------


def test_without_changes_scenario_9_applies(
    client: TestClient,
    boca: dict[str, str],
    ranking: Ranking,
    simulations: list[int],
) -> None:
    main = simulate(client, boca, DEFAULTS)
    simulations.clear()
    body = breakdown(client, boca, ranking.id, DEFAULTS)

    assert main["status"] == "no_changes"
    assert main["message"] == {"code": "NO_CHANGES", "text": NO_CHANGES}
    assert main["breakdown"] == {"status": "no_changes", "code": None, "message": None}
    assert simulations == []
    assert body == {
        "ranking_id": ranking.id,
        "status": "no_changes",
        "code": None,
        "message": None,
        "factors": [],
        "remainder": None,
        "non_additive_note": None,
    }


def test_the_same_values_written_differently_are_no_changes_too(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    values = {**DEFAULTS, "w_a": "0.60", "d_sat": "1200.0"}

    assert simulate(client, boca, values)["breakdown"]["status"] == "no_changes"
    assert breakdown(client, boca, ranking.id, values)["status"] == "no_changes"

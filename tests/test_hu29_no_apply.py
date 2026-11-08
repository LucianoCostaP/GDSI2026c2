"""HU-29, escenario 25: simular no pasa por HU-28 ni por HU-25 y no aplica nada.

"Given the simulator, When it runs, Then it does not require the real adjustment flow (HU-28)
nor a new official calculation (HU-25), and it offers no control to apply the values: to make
them official the Admin uses HU-28, which applies its own cut-off, lock and confirmation. The
result lists the changed parameters with their previous and hypothetical values so they can be
entered there."
Contrato: `docs/contrato-api-simulacion-reglas.md` §1 y §2, paso 7 (no hay botón "Aplicar").
"""

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.models import Ranking, RankingState, RulesVersion, User
from app.services.formula_service import get_in_force
from tests.conftest import BOCA_ID, Outbox
from tests.hu25_helpers import DEFAULTS, headers_for, make_ranking, publish_rules
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


def as_decimals(values: dict[str, str]) -> dict[str, Decimal]:
    # Las reglas se guardan en forma canónica (`0.6`, no `0.60`).
    return {key: Decimal(value) for key, value in values.items()}


# --- Aceptación ----------------------------------------------------------------------------


def test_the_simulator_offers_no_way_to_apply_the_values() -> None:
    routes = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith(SIMULATOR)
        for method in operations
    }

    # Abrir, simular, desglosar y descargar: ninguno escribe reglas.
    assert routes == {
        ("GET", SIMULATOR),
        ("POST", SIMULATOR),
        ("POST", f"{SIMULATOR}/breakdown"),
        ("POST", f"{SIMULATOR}/export"),
    }


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_writing_to_the_simulator_is_not_allowed(
    client: TestClient, boca: dict[str, str], ranking: Ranking, method: str
) -> None:
    response = client.request(method, SIMULATOR, json={"values": CHANGED}, headers=boca)

    assert response.status_code == 405


def test_simulating_leaves_the_rules_in_force_as_they_were(
    client: TestClient, db: Session, boca: dict[str, str], ranking: Ranking
) -> None:
    simulate(client, boca, CHANGED)

    in_force = get_in_force(db, BOCA_ID)
    assert in_force is not None
    assert in_force.number == 1
    assert as_decimals(in_force.values) == as_decimals(DEFAULTS)
    assert db.scalar(select(func.count()).select_from(RulesVersion)) == 1


def test_simulating_needs_no_adjustment_and_runs_no_ranking(
    client: TestClient, db: Session, boca: dict[str, str], ranking: Ranking
) -> None:
    # Las reglas nunca se ajustaron (HU-28) y no se calcula nada nuevo (HU-25).
    body = simulate(client, boca, CHANGED)

    assert body["status"] == "changed"
    assert db.scalar(select(func.count()).select_from(Ranking)) == 1


def test_a_ranking_being_calculated_does_not_stop_the_simulation(
    client: TestClient, db: Session, admin: User, boca: dict[str, str], ranking: Ranking
) -> None:
    make_ranking(db, admin, RankingState.RUNNING)

    body = simulate(client, boca, CHANGED)

    # Se compara contra el último completado; la corrida en curso no cuenta.
    assert body["ranking"]["id"] == ranking.id


def test_the_changed_parameters_can_be_entered_in_hu28_as_they_come(
    client: TestClient, db: Session, admin: User, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, CHANGED)
    entered = {p["key"]: p["after"] for p in body["changed_parameters"]}

    # HU-28 aplica su propio corte, bloqueo y confirmación.
    response = client.post(
        "/admin/formulas/adjust",
        json={
            "values": {**DEFAULTS, **entered},
            "expected_rules_version": body["ranking"]["rules_version"],
            "confirmed": True,
        },
        headers=boca,
    )
    assert response.status_code == 200, response.text

    in_force = get_in_force(db, BOCA_ID)
    assert in_force is not None
    assert as_decimals(in_force.values) == as_decimals(CHANGED)
    # Con esas reglas oficiales, el próximo cálculo es lo que se simuló: ya no hay cambios.
    run_ranking(db, admin)
    assert simulate(client, boca, CHANGED)["status"] == "no_changes"

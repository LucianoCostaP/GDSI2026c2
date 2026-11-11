"""HU-29, escenario 4: el último ranking no tiene socios.

"Given the latest completed ranking has no Socios, When a simulation is requested, Then it is
rejected with `EMPTY_RANKING` and nothing is calculated."
Contrato: `docs/contrato-api-simulacion-reglas.md` §1 (errores de dominio): abrir el simulador
no es error, responde 200 con `population_size = 0`.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Ranking, RankingState, RulesVersion, User
from tests.conftest import Outbox
from tests.hu25_helpers import (
    DEFAULTS,
    RUNS,
    headers_for,
    make_ranking,
    make_socio,
    publish_rules,
)

SIMULATOR = "/admin/rules-simulation"
EMPTY_RANKING = {
    "code": "EMPTY_RANKING",
    "message": "El último ranking no tiene socios: no hay nada para simular.",
}
COMPLETED_AT = datetime(2026, 10, 29, 15, 0, 3, tzinfo=UTC)


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


def calculate_ranking(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(RUNS, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def simulate(
    client: TestClient, headers: dict[str, str], values: dict[str, str] = DEFAULTS
):
    return client.post(SIMULATOR, json={"values": values}, headers=headers)


# --- Aceptación ----------------------------------------------------------------------------


def test_simulating_over_a_ranking_without_socios_is_rejected(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    # HU-25: un club sin socios igual obtiene un ranking completado, vacío.
    run = calculate_ranking(client, boca)
    assert run["population_size"] == 0
    versions_before = db.scalar(select(func.count()).select_from(RulesVersion))
    rankings_before = db.scalar(select(func.count()).select_from(Ranking))

    response = simulate(client, boca)

    assert response.status_code == 409
    assert response.json() == {"detail": EMPTY_RANKING}
    assert response.headers["cache-control"] == "no-store"
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(RulesVersion)) == versions_before
    assert db.scalar(select(func.count()).select_from(Ranking)) == rankings_before


def test_an_empty_ranking_is_rejected_before_looking_at_the_values(
    client: TestClient, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    calculate_ranking(client, boca)

    response = simulate(client, boca, {"d_sat": "no es un número"})

    assert response.status_code == 409
    assert response.json() == {"detail": EMPTY_RANKING}


def test_opening_the_simulator_over_an_empty_ranking_is_not_an_error(
    client: TestClient, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    run = calculate_ranking(client, boca)

    response = client.get(SIMULATOR, headers=boca)

    # El front ve `population_size = 0`, muestra el mensaje y no ofrece simular.
    assert response.status_code == 200, response.text
    assert response.json()["ranking"]["id"] == run["id"]
    assert response.json()["ranking"]["population_size"] == 0


def test_only_the_latest_completed_ranking_counts(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    """Un ranking anterior con socios no salva a uno vacío más nuevo, y al revés."""
    publish_rules(client, boca)
    make_socio(db)
    calculate_ranking(client, boca)
    # Uno vacío, completado después: es la base.
    make_ranking(
        db,
        admin,
        RankingState.COMPLETED,
        calculated_at=datetime(2030, 1, 1, tzinfo=UTC),
        completed_at=datetime(2030, 1, 1, 0, 1, tzinfo=UTC),
    )

    assert simulate(client, boca).json() == {"detail": EMPTY_RANKING}


def test_a_ranking_with_socios_can_be_simulated(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_ranking(
        db,
        admin,
        RankingState.COMPLETED,
        calculated_at=COMPLETED_AT - timedelta(minutes=1),
        completed_at=COMPLETED_AT,
    )
    make_socio(db)
    run = calculate_ranking(client, boca)

    response = simulate(client, boca)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ranking"]["id"] == run["id"]
    assert body["ranking"]["population_size"] == 1
    assert response.headers["cache-control"] == "no-store"

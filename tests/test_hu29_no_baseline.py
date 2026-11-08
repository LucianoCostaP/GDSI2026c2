"""HU-29, escenario 3: sin ranking completado no hay con qué comparar.

"Given no completed ranking exists (none ever calculated, or only `running` or `failed` ones),
When the Admin opens the simulator or requests a simulation, Then the message `NO_BASELINE` is
shown and no form is offered. A ranking in `running` state does not change the baseline: it is
still the latest `completed` one."
Contrato: `docs/contrato-api-simulacion-reglas.md` §1 (errores de dominio) y §3.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import RankingState, User
from tests.conftest import Outbox
from tests.hu25_helpers import (
    DEFAULTS,
    adjust_rules,
    headers_for,
    make_ranking,
    publish_rules,
)

SIMULATOR = "/admin/rules-simulation"
NO_BASELINE = {
    "code": "NO_BASELINE",
    "message": "Todavía no hay un ranking calculado, así que no hay con qué comparar. "
    "Calculá el ranking para poder simular.",
}
COMPLETED_AT = datetime(2026, 10, 29, 15, 0, 3, tzinfo=UTC)


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


def assert_no_baseline(client: TestClient, headers: dict[str, str]) -> None:
    """Tanto al abrir el simulador como al pedir una simulación."""
    opened = client.get(SIMULATOR, headers=headers)
    run = client.post(SIMULATOR, json={"values": DEFAULTS}, headers=headers)

    for response in (opened, run):
        assert response.status_code == 409
        # Solo el error: ni ranking, ni formulario, ni valores para precargar.
        assert response.json() == {"detail": NO_BASELINE}
        assert response.headers["cache-control"] == "no-store"


# --- Aceptación: no hay ranking completado -------------------------------------------------


def test_without_any_ranking_there_is_nothing_to_compare_against(
    client: TestClient, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)

    assert_no_baseline(client, boca)


def test_without_published_rules_nor_ranking_there_is_no_baseline_either(
    client: TestClient, boca: dict[str, str]
) -> None:
    assert_no_baseline(client, boca)


@pytest.mark.parametrize("state", [RankingState.RUNNING, RankingState.FAILED])
def test_a_ranking_that_did_not_complete_is_not_a_baseline(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    state: RankingState,
) -> None:
    publish_rules(client, boca)
    make_ranking(db, admin, state)

    assert_no_baseline(client, boca)


def test_only_failed_and_running_rankings_are_no_baseline(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_ranking(db, admin, RankingState.FAILED)
    make_ranking(db, admin, RankingState.FAILED)
    make_ranking(db, admin, RankingState.RUNNING)

    assert_no_baseline(client, boca)


# --- Aceptación: una corrida en curso o fallida no cambia la base --------------------------


@pytest.mark.parametrize("state", [RankingState.RUNNING, RankingState.FAILED])
def test_a_later_run_that_did_not_complete_keeps_the_latest_completed_baseline(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    state: RankingState,
) -> None:
    publish_rules(client, boca)
    completed = make_ranking(
        db,
        admin,
        RankingState.COMPLETED,
        calculated_at=COMPLETED_AT - timedelta(minutes=1),
        completed_at=COMPLETED_AT,
    )
    # La corrida posterior usa otras reglas: si se tomara como base, cambiaría la versión.
    adjust_rules(client, boca, 1, d_sat="1500")
    make_ranking(db, admin, state, calculated_at=COMPLETED_AT + timedelta(hours=2))

    response = client.get(SIMULATOR, headers=boca)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ranking"]["id"] == completed.id
    assert body["ranking"]["rules_version"] == 1
    assert body["baseline_text"] == (
        "Comparado con el ranking calculado el 29/10/2026 12:00 (reglas versión 1)."
    )


def test_the_baseline_is_the_latest_completed_ranking(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_ranking(db, admin, RankingState.COMPLETED, completed_at=COMPLETED_AT)
    newest = make_ranking(
        db,
        admin,
        RankingState.COMPLETED,
        calculated_at=COMPLETED_AT + timedelta(days=1),
        completed_at=COMPLETED_AT + timedelta(days=1),
    )
    make_ranking(
        db, admin, RankingState.RUNNING, calculated_at=COMPLETED_AT + timedelta(days=2)
    )

    body = client.get(SIMULATOR, headers=boca).json()

    assert body["ranking"]["id"] == newest.id
    assert body["baseline_text"] == (
        "Comparado con el ranking calculado el 30/10/2026 12:00 (reglas versión 1)."
    )

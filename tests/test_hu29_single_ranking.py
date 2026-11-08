"""HU-29, escenario 10: cada resultado usa un solo ranking.

"Given a new ranking completes while a simulation is running, or between two runs, When the
result is shown, Then each result uses a single ranking, the one that was the latest completed
at the moment the run started, and its date and rules version are shown (scenario 1); results
of two rankings are never mixed." Contrato: `docs/contrato-api-simulacion-reglas.md` §5.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, User
from app.scoring.rules_simulation import StoredEntry
from app.services import rules_simulation_service
from app.services.rules_simulation_service import baseline_text
from tests.conftest import Outbox
from tests.hu25_helpers import (
    DEFAULTS,
    adjust_rules,
    headers_for,
    make_socio,
    publish_rules,
)
from tests.hu29_helpers import CHANGED, SIMULATOR, make_varied_club, run_ranking


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


@pytest.fixture
def first(db: Session, admin: User, boca: dict[str, str]) -> Ranking:
    """El ranking base: 7 socios, reglas versión 1."""
    make_varied_club(db)
    return run_ranking(db, admin)


def simulate(
    client: TestClient, headers: dict[str, str], values: dict[str, Any]
) -> Any:
    response = client.post(SIMULATOR, json={"values": values}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def complete_a_new_ranking(
    client: TestClient, db: Session, admin: User, headers: dict[str, str]
) -> Ranking:
    """Otro ranking, con otras reglas (versión 2) y dos socios más."""
    adjust_rules(client, headers, 1, **CHANGED)
    make_socio(db)
    make_socio(db)
    return run_ranking(db, admin)


def assert_uses(body: dict[str, Any], ranking: Ranking, rules_version: int) -> None:
    assert ranking.completed_at is not None
    assert body["ranking"]["id"] == ranking.id
    assert body["ranking"]["rules_version"] == rules_version
    assert body["ranking"]["population_size"] == ranking.population_size
    assert body["baseline_text"] == baseline_text(ranking.completed_at, rules_version)
    # Las posiciones salen de ese ranking: suben + bajan + igual es su población.
    moved = body["movement"]
    assert moved["up"] + moved["down"] + moved["unchanged"] == ranking.population_size


# --- Aceptación: entre dos simulaciones ----------------------------------------------------


def test_a_ranking_completed_between_two_runs_is_used_by_the_next_one(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    first: Ranking,
) -> None:
    before = simulate(client, boca, CHANGED)
    second = complete_a_new_ranking(client, db, admin, boca)

    after = simulate(client, boca, CHANGED)

    assert_uses(before, first, 1)
    assert before["status"] == "changed"
    assert_uses(after, second, 2)
    # Los valores se comparan con las reglas del ranking nuevo, que ya son esos.
    assert after["status"] == "no_changes"
    assert after["changed_parameters"] == []


def test_the_simulator_form_follows_the_new_ranking_too(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    first: Ranking,
) -> None:
    opened_before = client.get(SIMULATOR, headers=boca).json()
    second = complete_a_new_ranking(client, db, admin, boca)
    opened_after = client.get(SIMULATOR, headers=boca).json()

    assert opened_before["ranking"]["id"] == first.id
    assert opened_before["values"]["d_sat"] == DEFAULTS["d_sat"]
    assert opened_after["ranking"]["id"] == second.id
    assert opened_after["ranking"]["population_size"] == 9
    assert opened_after["values"]["d_sat"] == CHANGED["d_sat"]


# --- Aceptación: un ranking que termina en medio de la simulación --------------------------


def test_a_ranking_completed_during_a_run_does_not_mix_into_its_result(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    first: Ranking,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    undisturbed = simulate(client, boca, CHANGED)
    original: Callable[[Session, int], list[StoredEntry]] = (
        rules_simulation_service.stored_entries
    )
    completed: list[Ranking] = []

    def a_new_ranking_completes_first(
        session: Session, ranking_id: int
    ) -> list[StoredEntry]:
        # La base ya se fijó; justo entonces termina otro cálculo (una sola vez).
        if not completed:
            completed.append(complete_a_new_ranking(client, db, admin, boca))
        return original(session, ranking_id)

    monkeypatch.setattr(
        rules_simulation_service, "stored_entries", a_new_ranking_completes_first
    )

    body = simulate(client, boca, CHANGED)

    [second] = completed
    assert second.id != first.id and second.population_size == 9
    # El resultado es entero del ranking que era el último al empezar.
    assert_uses(body, first, 1)
    assert body == undisturbed


def test_the_next_run_after_that_uses_the_new_ranking(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    first: Ranking,
) -> None:
    second = complete_a_new_ranking(client, db, admin, boca)

    body = simulate(client, boca, DEFAULTS)

    # Contra las reglas del ranking nuevo, los valores por defecto sí son un cambio.
    assert_uses(body, second, 2)
    assert body["status"] == "changed"
    assert {p["key"]: p["before"] for p in body["changed_parameters"]}["d_sat"] == "600"

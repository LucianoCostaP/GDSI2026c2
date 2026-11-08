"""HU-29, escenario 9: con los valores del ranking no cambia nada.

"Given hypothetical values identical to the rules version of the ranking, When it runs, Then
every simulated component, total and position equals the stored one, 0 Socios go up and 0 go
down, the distributions are equal, every change per component is 0, and the message
`NO_CHANGES` is shown." Contrato: `docs/contrato-api-simulacion-reglas.md` §5.1.

Las distribuciones y los cambios por componente son secciones de los escenarios 11 a 16: sus
tests cubren también el caso sin cambios.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, User
from app.scoring.components import COMPONENT_KEYS
from app.scoring.engine import ScoringParameters
from app.scoring.rules_simulation import simulate_entries
from app.services.rules_simulation_service import stored_entries
from tests.conftest import Outbox
from tests.hu25_helpers import DEFAULTS, adjust_rules, headers_for, publish_rules
from tests.hu29_helpers import (
    CHANGED,
    SIMULATOR,
    VariedClub,
    make_varied_club,
    run_ranking,
)

NO_CHANGES = {
    "code": "NO_CHANGES",
    "text": "Los valores son iguales a los del ranking: no hay diferencias para mostrar.",
}


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


@pytest.fixture
def ranking(db: Session, admin: User, boca: dict[str, str]) -> Ranking:
    club: VariedClub = make_varied_club(db)
    assert len(club.socios) == 7
    return run_ranking(db, admin)


def simulate(
    client: TestClient, headers: dict[str, str], values: dict[str, Any]
) -> Any:
    response = client.post(SIMULATOR, json={"values": values}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def assert_no_changes(body: dict[str, Any], population: int) -> None:
    assert body["status"] == "no_changes"
    assert body["message"] == NO_CHANGES
    assert body["changed_parameters"] == []
    assert body["factors_changed"] == []
    assert body["movement"] == {
        "up": 0,
        "down": 0,
        "unchanged": population,
        "mean_abs_position_change": "0.0",
        "relevant_threshold": 1,
        "relevant_up": 0,
        "relevant_down": 0,
    }


# --- Aceptación ----------------------------------------------------------------------------


def test_with_the_values_of_the_ranking_nothing_changes(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, DEFAULTS)

    assert_no_changes(body, 7)


def test_every_simulated_component_total_and_position_equals_the_stored_one(
    db: Session, ranking: Ranking
) -> None:
    stored = stored_entries(db, ranking.id)
    simulated = simulate_entries(stored, ScoringParameters.from_values(DEFAULTS))

    assert len(simulated) == 7
    for before, after in zip(stored, simulated, strict=True):
        assert after.socio_id == before.socio_id
        assert after.position == before.position
        assert after.total == before.total
        assert {k: after.components[k] for k in COMPONENT_KEYS} == dict(
            before.components
        )


@pytest.mark.parametrize(
    "values",
    [
        {**DEFAULTS, "w_a": "0.600", "d_sat": "1200.0", "gamma": "1"},
        {**DEFAULTS, "w_a": 0.6, "d_sat": 1200, "b_max": 15},
        {**DEFAULTS, "alpha_t": "0,70", "t_ref": " 50 "},
    ],
    ids=["ceros-de-mas", "numeros-json", "coma-y-espacios"],
)
def test_the_same_values_written_differently_are_no_changes(
    client: TestClient, boca: dict[str, str], ranking: Ranking, values: dict[str, Any]
) -> None:
    assert_no_changes(simulate(client, boca, values), 7)


def test_the_comparison_is_against_the_rules_of_the_ranking_not_the_ones_in_force(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    # Después del ranking rigen otras reglas (HU-28): la versión 2.
    adjust_rules(client, boca, 1, **CHANGED)

    with_ranking_rules = simulate(client, boca, DEFAULTS)
    with_rules_in_force = simulate(client, boca, CHANGED)

    assert_no_changes(with_ranking_rules, 7)
    assert with_rules_in_force["status"] == "changed"
    assert with_rules_in_force["message"] is None


def test_repeating_the_simulation_gives_the_same_result(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    first = simulate(client, boca, CHANGED)
    unchanged = simulate(client, boca, DEFAULTS)
    second = simulate(client, boca, CHANGED)

    assert first == second
    assert_no_changes(unchanged, 7)


def test_a_single_changed_value_is_not_no_changes(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, {**DEFAULTS, "t_carencia": "366"})

    assert body["status"] == "changed"
    assert [p["key"] for p in body["changed_parameters"]] == ["t_carencia"]
    assert body["factors_changed"] == ["other"]

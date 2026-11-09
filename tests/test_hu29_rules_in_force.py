"""HU-29, escenario 2: las reglas vigentes no son las del ranking.

"Given the rules in force differ from the rules version of the ranking (for example, right
after an adjustment in HU-28), When the simulator is opened, Then a notice states both versions
and offers a control to load the rules in force into the form. Loading them only fills the
form: it does not run the simulation and does not change anything real."
Contrato: `docs/contrato-api-simulacion-reglas.md` §3 (`rules_in_force`).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Ranking, RulesVersion, RulesVersionState, User
from app.scoring.catalog import SCORING_MODEL_V1
from app.services.rules_simulation_service import rules_in_force_notice
from tests.conftest import BOCA_ID, Outbox
from tests.hu25_helpers import (
    RUNS,
    adjust_rules,
    headers_for,
    make_socio,
    publish_rules,
)

SIMULATOR = "/admin/rules-simulation"
PARAMETER_KEYS = [p.key for p in SCORING_MODEL_V1.parameters]


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


def calculate_ranking(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(RUNS, headers=headers)
    assert response.status_code == 201, response.text


def rules_in_force_number(db: Session) -> int:
    return db.scalars(
        select(RulesVersion.number).where(
            RulesVersion.club_id == BOCA_ID,
            RulesVersion.state == RulesVersionState.IN_FORCE,
        )
    ).one()


# --- Aceptación ----------------------------------------------------------------------------


def test_after_an_adjustment_the_simulator_offers_the_rules_in_force(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca, d_sat="800")
    make_socio(db)
    calculate_ranking(client, boca)
    adjust_rules(client, boca, 1, d_sat="1500", w_a="0.55", w_t="0.25")

    body = client.get(SIMULATOR, headers=boca).json()

    in_force = body["rules_in_force"]
    assert in_force["differs"] is True
    assert in_force["version"] == 2
    assert in_force["notice"] == (
        "Las reglas vigentes (versión 2) son distintas de las del ranking (versión 1). "
        "Podés cargarlas acá para ver cómo cambiaría el ranking en el próximo cálculo."
    )
    # Valores para cargar en el formulario: todos, en el orden de la fórmula.
    assert list(in_force["values"]) == PARAMETER_KEYS
    assert in_force["values"]["d_sat"] == "1500"
    assert in_force["values"]["w_a"] == "0.55"
    assert in_force["values"]["w_t"] == "0.25"
    # El formulario sigue precargado con las reglas del ranking (escenario 1).
    assert body["ranking"]["rules_version"] == 1
    assert body["values"]["d_sat"] == "800"
    assert body["values"]["w_a"] == "0.6"


def test_with_several_adjustments_the_latest_rules_in_force_are_offered(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    calculate_ranking(client, boca)
    adjust_rules(client, boca, 1, d_sat="1500")
    adjust_rules(client, boca, 2, d_sat="2000")

    in_force = client.get(SIMULATOR, headers=boca).json()["rules_in_force"]

    assert in_force["version"] == 3
    assert in_force["values"]["d_sat"] == "2000"
    assert in_force["notice"] == rules_in_force_notice(3, 1)


def test_when_the_ranking_uses_the_rules_in_force_there_is_no_notice(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    calculate_ranking(client, boca)

    body = client.get(SIMULATOR, headers=boca).json()

    assert body["rules_in_force"] == {
        "differs": False,
        "version": None,
        "values": None,
        "notice": None,
    }


def test_a_ranking_calculated_after_the_adjustment_uses_the_rules_in_force(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    calculate_ranking(client, boca)
    adjust_rules(client, boca, 1, d_sat="1500")
    calculate_ranking(client, boca)

    body = client.get(SIMULATOR, headers=boca).json()

    assert body["ranking"]["rules_version"] == 2
    assert body["values"]["d_sat"] == "1500"
    assert body["rules_in_force"]["differs"] is False


def test_offering_the_rules_in_force_changes_nothing(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    calculate_ranking(client, boca)
    adjust_rules(client, boca, 1, d_sat="1500")
    versions_before = db.scalar(select(func.count()).select_from(RulesVersion))
    rankings_before = db.scalar(select(func.count()).select_from(Ranking))

    client.get(SIMULATOR, headers=boca)
    client.get(SIMULATOR, headers=boca)

    db.expire_all()
    assert db.scalar(select(func.count()).select_from(RulesVersion)) == versions_before
    assert db.scalar(select(func.count()).select_from(Ranking)) == rankings_before
    assert rules_in_force_number(db) == 2


# --- Unitarias -----------------------------------------------------------------------------


def test_rules_in_force_notice_names_both_versions() -> None:
    assert rules_in_force_notice(5, 3) == (
        "Las reglas vigentes (versión 5) son distintas de las del ranking (versión 3). "
        "Podés cargarlas acá para ver cómo cambiaría el ranking en el próximo cálculo."
    )

"""HU-29, escenario 24: repetir la simulación cuantas veces se quiera.

"Given a finished simulation, When the Admin changes the values, Then it can be repeated as
many times as wanted; each run is independent and nothing accumulates between runs."
Contrato: `docs/contrato-api-simulacion-reglas.md` §1 (repetir no acumula nada) y §2, paso 7.
"""

import copy
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    FormulaLock,
    Ranking,
    RankingEntry,
    RulesVersion,
    User,
)
from app.scoring.engine import ScoringParameters
from app.scoring.rules_simulation import PillarSimulator, simulate_entries
from app.services.rules_simulation_service import stored_entries
from tests.conftest import Outbox
from tests.hu25_helpers import DEFAULTS, entries_of, headers_for, publish_rules
from tests.hu29_helpers import (
    CHANGED,
    FLATTER,
    SIMULATOR,
    SPREAD,
    TO_THE_CAP,
    make_saturation_club,
    run_ranking,
)

BREAKDOWN = f"{SIMULATOR}/breakdown"


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


def breakdown(
    client: TestClient, headers: dict[str, str], ranking_id: int, values: dict[str, Any]
) -> Any:
    response = client.post(
        BREAKDOWN, json={"ranking_id": ranking_id, "values": values}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- Aceptación ----------------------------------------------------------------------------


def test_the_same_values_give_the_same_result_whatever_ran_before(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    first = {
        name: simulate(client, boca, v) for name, v in (("a", SPREAD), ("b", FLATTER))
    }

    # Otro orden, con simulaciones en el medio: cada una es independiente.
    again_b = simulate(client, boca, FLATTER)
    simulate(client, boca, TO_THE_CAP)
    again_a = simulate(client, boca, SPREAD)

    assert again_a == first["a"]
    assert again_b == first["b"]


def test_the_comparison_is_always_against_the_ranking_not_the_previous_run(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    simulate(client, boca, {**DEFAULTS, "d_sat": "800"})

    body = simulate(client, boca, {**DEFAULTS, "d_sat": "600"})
    back = simulate(client, boca, DEFAULTS)

    # "Antes" sigue siendo el valor del ranking, no el de la corrida anterior.
    assert [
        (p["key"], p["before"], p["after"]) for p in body["changed_parameters"]
    ] == [("d_sat", "1200", "600")]
    # Volver a los valores del ranking no deja nada acumulado: no hay cambios.
    assert back["status"] == "no_changes"
    assert back["movement"]["unchanged"] == ranking.population_size


def test_the_breakdown_can_be_repeated_too(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    first = breakdown(client, boca, ranking.id, SPREAD)
    breakdown(client, boca, ranking.id, CHANGED)
    simulate(client, boca, TO_THE_CAP)

    assert breakdown(client, boca, ranking.id, SPREAD) == first


def test_repeating_as_many_times_as_wanted_stores_nothing(
    client: TestClient, db: Session, boca: dict[str, str], ranking: Ranking
) -> None:
    def state() -> tuple[Any, ...]:
        counts = tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (Ranking, RankingEntry, RulesVersion, AuditLog, FormulaLock)
        )
        stored = sorted(
            (e.socio_id, e.position, e.total) for e in entries_of(db, ranking)
        )
        return counts, stored

    before = state()

    # Sin límite de repeticiones: todas responden.
    for values in [SPREAD, FLATTER, TO_THE_CAP, CHANGED, DEFAULTS] * 3:
        simulate(client, boca, values)
    for values in [SPREAD, CHANGED]:
        breakdown(client, boca, ranking.id, values)

    db.expire_all()
    assert state() == before


# --- Unitarias -----------------------------------------------------------------------------


def test_a_simulation_does_not_change_the_entries_it_reads(
    db: Session, ranking: Ranking
) -> None:
    entries = stored_entries(db, ranking.id)
    untouched = copy.deepcopy(entries)

    simulate_entries(entries, ScoringParameters.from_values(SPREAD))
    PillarSimulator(entries).run(ScoringParameters.from_values(CHANGED))

    assert entries == untouched


def test_reusing_the_pillars_does_not_carry_one_run_into_the_next(
    db: Session, ranking: Ranking
) -> None:
    # Dentro de un desglose el simulador reusa pilares: el orden de las corridas no importa.
    entries = stored_entries(db, ranking.id)
    simulator = PillarSimulator(entries)
    spread = simulator.run(ScoringParameters.from_values(SPREAD))
    simulator.run(ScoringParameters.from_values(CHANGED))

    assert simulator.run(ScoringParameters.from_values(SPREAD)) == spread
    assert PillarSimulator(entries).run(ScoringParameters.from_values(SPREAD)) == spread

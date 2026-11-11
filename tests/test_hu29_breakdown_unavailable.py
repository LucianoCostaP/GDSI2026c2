"""HU-29, escenario 21: el desglose no frena el resultado principal y puede no estar.

"Given the isolated simulations are slower than the main result, When the Admin runs a
simulation, Then the main result (scenarios 8 to 16 and the equity analysis of HU-30) is shown
first and the effect by parameter is shown as soon as it is ready, with a "calculando"
indicator in the meantime. Given the isolated simulations fail or do not finish within their
target, Then the main result stays shown and the section shows `BREAKDOWN_UNAVAILABLE`."
Contrato: `docs/contrato-api-simulacion-reglas.md` §2 (pasos 4 y 5), §6 y §8; SC-006.
"""

import itertools
import uuid
from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, User
from app.scoring import rules_simulation
from app.scoring.rules_simulation import (
    BreakdownTimeout,
    Deadline,
    PillarSimulator,
    StoredEntry,
    breakdown_budget,
)
from app.services import rules_simulation_service
from app.services.rules_simulation_service import breakdown, stored_entries
from tests.conftest import BOCA_ID, Outbox
from tests.hu25_helpers import headers_for, publish_rules
from tests.hu29_helpers import SIMULATOR, SPREAD, make_saturation_club, run_ranking

BREAKDOWN = f"{SIMULATOR}/breakdown"
UNAVAILABLE = {
    "status": "unavailable",
    "code": "BREAKDOWN_UNAVAILABLE",
    "message": (
        "No pudimos calcular el efecto de cada parámetro. "
        "El resultado general sigue siendo válido."
    ),
    "factors": [],
    "remainder": None,
    "non_additive_note": None,
}


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


@pytest.fixture
def ranking(db: Session, admin: User, boca: dict[str, str]) -> Ranking:
    make_saturation_club(db)
    return run_ranking(db, admin)


def post_breakdown(client: TestClient, headers: dict[str, str], ranking_id: int) -> Any:
    response = client.post(
        BREAKDOWN, json={"ranking_id": ranking_id, "values": SPREAD}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def clock(*readings: float) -> Callable[[], float]:
    """Un reloj que da esas lecturas y después repite la última."""
    values: Iterator[float] = itertools.chain(readings, itertools.repeat(readings[-1]))
    return lambda: next(values)


# --- Aceptación: el resultado principal no espera ------------------------------------------


def test_the_main_result_comes_first_and_says_the_breakdown_is_being_calculated(
    client: TestClient,
    boca: dict[str, str],
    ranking: Ranking,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # El resultado principal no corre ninguna simulación aislada: solo la completa.
    runs: list[int] = []
    original = rules_simulation.simulate_entries

    def counting(*args: Any) -> Any:
        runs.append(1)
        return original(*args)

    monkeypatch.setattr(rules_simulation_service, "simulate_entries", counting)
    monkeypatch.setattr(rules_simulation_service, "PillarSimulator", None)

    response = client.post(SIMULATOR, json={"values": SPREAD}, headers=boca)

    assert response.status_code == 200, response.text
    assert runs == [1]
    assert response.json()["breakdown"] == {
        "status": "pending",
        "code": None,
        "message": "Calculando el efecto de cada parámetro…",
    }


# --- Aceptación: falla o tiempo máximo -----------------------------------------------------


def test_if_the_breakdown_fails_it_is_unavailable_and_the_main_result_stays(
    client: TestClient,
    boca: dict[str, str],
    ranking: Ranking,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(self: PillarSimulator, params: Any) -> Any:
        raise ArithmeticError("falla de prueba")

    monkeypatch.setattr(PillarSimulator, "run", broken)

    body = post_breakdown(client, boca, ranking.id)
    main = client.post(SIMULATOR, json={"values": SPREAD}, headers=boca)

    assert body == {"ranking_id": ranking.id, **UNAVAILABLE}
    assert main.status_code == 200
    assert main.json()["status"] == "changed"
    assert main.json()["breakdown"]["status"] == "pending"


def test_past_its_target_time_the_breakdown_is_unavailable(
    db: Session, ranking: Ranking
) -> None:
    # Arranca en 0 y a la primera mirada ya pasaron 10 s: más que los 9 s de un club chico.
    body = breakdown(db, BOCA_ID, ranking.id, SPREAD, clock=clock(0, 10))

    assert body.model_dump() == {"ranking_id": ranking.id, **UNAVAILABLE}


def test_right_at_its_target_time_the_breakdown_is_still_available(
    db: Session, ranking: Ranking
) -> None:
    body = breakdown(db, BOCA_ID, ranking.id, SPREAD, clock=clock(0, 9))

    assert body.status == "available"
    assert len(body.factors) == 3


def test_the_time_is_counted_from_the_request_not_per_simulation(
    db: Session, ranking: Ranking
) -> None:
    # Cada mirada suma 1 s: ninguna simulación sola pasa de 9 s, pero todas juntas sí.
    seconds = itertools.count()

    body = breakdown(db, BOCA_ID, ranking.id, SPREAD, clock=lambda: next(seconds))

    assert body.status == "unavailable"


def test_the_rejections_still_come_before_the_time(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    response = client.post(
        BREAKDOWN,
        json={"ranking_id": ranking.id, "values": {**SPREAD, "w_a": "2"}},
        headers=boca,
    )

    assert response.status_code == 422


# --- Unitarias -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("population", "seconds"),
    [(1, 9), (50_000, 9), (50_001, 30), (500_000, 30), (900_000, 30)],
)
def test_the_target_is_9_seconds_up_to_50000_socios_and_30_above(
    population: int, seconds: int
) -> None:
    assert breakdown_budget(population) == seconds


def test_the_deadline_is_passed_only_after_its_seconds() -> None:
    readings = iter([100.0, 108.5, 109.0, 109.01])
    deadline = Deadline(9, lambda: next(readings))

    deadline.check()
    deadline.check()
    with pytest.raises(BreakdownTimeout):
        deadline.check()


def many(entries: list[StoredEntry], copies: int) -> list[StoredEntry]:
    return [
        replace(entry, socio_id=uuid.uuid4())
        for _ in range(copies)
        for entry in entries
    ]


def test_the_clock_is_checked_inside_each_recalculation(
    db: Session, ranking: Ranking
) -> None:
    # 2.750 socios: el reloj se mira cada 1.000, así que corta en medio de la lectura.
    entries = many(stored_entries(db, ranking.id), 250)
    checks: list[int] = []

    def checkpoint() -> None:
        checks.append(1)
        if len(checks) == 2:
            raise BreakdownTimeout

    with pytest.raises(BreakdownTimeout):
        PillarSimulator(entries, checkpoint)

    assert len(checks) == 2

"""HU-29, escenario 7: el bloqueo y el corte de temporada no frenan la simulación.

"Given the formula is locked (HU-27), or the season cut-off of HU-28 has passed, When the Admin
simulates, Then the simulation runs normally: those two rules govern **saving** official rules,
not previewing them. The limits and the sum rule are those of the formula of the ranking's
rules version." Contrato: `docs/contrato-api-simulacion-reglas.md` §3 y §4.1.
"""

import dataclasses
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models import FormulaLock, FormulaLockState, User
from app.scoring.catalog import SCORING_MODEL_V1, FormulaDescriptor
from app.services import rules_simulation_service
from tests.conftest import BOCA_ID, Outbox
from tests.hu25_helpers import DEFAULTS, RUNS, headers_for, make_socio, publish_rules

SIMULATOR = "/admin/rules-simulation"
CHANGED = {**DEFAULTS, "w_a": "0.65", "w_t": "0.15", "d_sat": "800"}


@pytest.fixture
def boca(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> dict[str, str]:
    """Admin de Boca con un ranking completado de un socio."""
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    make_socio(db)
    response = client.post(RUNS, headers=headers)
    assert response.status_code == 201, response.text
    return headers


def lock_formula(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(
        "/admin/formulas/lock", json={"reason": "Temporada en curso"}, headers=headers
    )
    assert response.status_code == 200, response.text


def adjust(client: TestClient, headers: dict[str, str]) -> Any:
    return client.post(
        "/admin/formulas/adjust",
        json={"values": CHANGED, "expected_rules_version": 1, "confirmed": True},
        headers=headers,
    )


def pass_the_season_cutoff(monkeypatch: pytest.MonkeyPatch) -> None:
    # La temporada empezó hace un mes: el corte (14 días antes) ya pasó.
    monkeypatch.setattr(
        settings, "season_start_date", date.today() - timedelta(days=30)
    )


# --- Aceptación ----------------------------------------------------------------------------


def test_a_locked_formula_can_still_be_simulated(
    client: TestClient, boca: dict[str, str]
) -> None:
    lock_formula(client, boca)
    # Guardar reglas oficiales sí está bloqueado...
    assert adjust(client, boca).json()["detail"]["code"] == "FORMULA_LOCKED"

    # ...simular no.
    response = client.post(SIMULATOR, json={"values": CHANGED}, headers=boca)

    assert response.status_code == 200, response.text


def test_simulating_leaves_the_formula_locked(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    # Edge case "No effect on real data": el bloqueo nunca cambia.
    lock_formula(client, boca)
    lock = db.get_one(FormulaLock, BOCA_ID)
    before = (lock.state, lock.reason, lock.changed_by_id, lock.changed_at)

    response = client.post(SIMULATOR, json={"values": CHANGED}, headers=boca)
    assert response.status_code == 200, response.text

    db.expire_all()
    lock = db.get_one(FormulaLock, BOCA_ID)
    assert (lock.state, lock.reason, lock.changed_by_id, lock.changed_at) == before
    assert lock.state == FormulaLockState.LOCKED
    assert adjust(client, boca).json()["detail"]["code"] == "FORMULA_LOCKED"


def test_after_the_season_cutoff_the_formula_can_still_be_simulated(
    client: TestClient, boca: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    pass_the_season_cutoff(monkeypatch)
    assert adjust(client, boca).json()["detail"]["code"] == "SEASON_CUTOFF_REACHED"

    response = client.post(SIMULATOR, json={"values": CHANGED}, headers=boca)

    assert response.status_code == 200, response.text


def test_locked_and_after_the_cutoff_the_simulator_still_opens_and_runs(
    client: TestClient, boca: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_formula(client, boca)
    pass_the_season_cutoff(monkeypatch)

    opened = client.get(SIMULATOR, headers=boca)
    run = client.post(SIMULATOR, json={"values": CHANGED}, headers=boca)

    assert opened.status_code == 200, opened.text
    assert run.status_code == 200, run.text
    # Ni el bloqueo ni el corte aparecen en el simulador.
    assert "lock" not in opened.json()
    assert "season_cutoff" not in opened.json()


def test_locked_values_are_still_validated(
    client: TestClient, boca: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """El bloqueo y el corte no saltean la validación: solo no la reemplazan."""
    lock_formula(client, boca)
    pass_the_season_cutoff(monkeypatch)

    response = client.post(
        SIMULATOR, json={"values": {**DEFAULTS, "d_sat": "10"}}, headers=boca
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_VALUES"


def test_the_limits_are_those_of_the_formula_of_the_ranking_rules(
    client: TestClient, boca: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con una sola fórmula en el catálogo, se cambia el descriptor que devuelve el catálogo
    para ver que la validación usa el de la fórmula de las reglas del ranking."""
    asked: list[tuple[str, int]] = []
    narrower = dataclasses.replace(
        SCORING_MODEL_V1,
        parameters=tuple(
            dataclasses.replace(p, maximum=p.maximum / 3) if p.key == "d_sat" else p
            for p in SCORING_MODEL_V1.parameters
        ),
    )

    def get_descriptor(formula_id: str, version: int) -> FormulaDescriptor | None:
        asked.append((formula_id, version))
        return narrower

    monkeypatch.setattr(rules_simulation_service, "get_descriptor", get_descriptor)

    response = client.post(
        SIMULATOR, json={"values": {**DEFAULTS, "d_sat": "1500"}}, headers=boca
    )

    assert response.status_code == 422
    [violation] = response.json()["detail"]["violations"]
    assert violation["message"] == (
        "«Distancia de saturación» tiene que estar entre 50 y 1000 km."
    )
    assert set(asked) == {("scoring-model", 1)}

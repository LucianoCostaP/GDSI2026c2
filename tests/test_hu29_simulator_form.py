"""HU-29, escenario 1: abrir el simulador con el formulario precargado.

"Given an Admin logged in and a completed ranking, When they open the simulator, Then every
parameter of the formula is shown pre-filled with the values of the rules version of that
ranking, with its limits and the derived values of the formula (`b`) read-only; and a line
states the baseline." Contrato: `docs/contrato-api-simulacion-reglas.md` §3.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, RankingState, User
from app.scoring.catalog import SCORING_MODEL_V1
from app.scoring.derived import derived_values
from app.scoring.engine import distance_slope
from app.services.rules_simulation_service import baseline_text
from tests.conftest import Outbox
from tests.hu25_helpers import (
    RUNS,
    adjust_rules,
    headers_for,
    make_ranking,
    make_socio,
    publish_rules,
)

SIMULATOR = "/admin/rules-simulation"
PARAMETER_KEYS = [p.key for p in SCORING_MODEL_V1.parameters]


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


def calculate_ranking(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(RUNS, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# --- Aceptación ----------------------------------------------------------------------------


def test_opening_the_simulator_shows_the_baseline_ranking_and_its_rules(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca, d_sat="800", w_a="0.50", w_p="0.30")
    make_socio(db)
    make_socio(db)
    run = calculate_ranking(client, boca)

    response = client.get(SIMULATOR, headers=boca)

    assert response.status_code == 200, response.text
    body = response.json()
    ranking = db.get_one(Ranking, run["id"])
    assert ranking.completed_at is not None
    assert body["ranking"] == {
        "id": run["id"],
        "completed_at": run["completed_at"],
        "calculation_date": run["calculation_date"],
        "rules_version": 1,
        "population_size": 2,
    }
    assert body["baseline_text"] == baseline_text(ranking.completed_at, 1)
    # Todos los parámetros de la fórmula, con los valores de las reglas del ranking.
    assert list(body["values"]) == PARAMETER_KEYS
    assert body["values"]["d_sat"] == "800"
    assert body["values"]["w_a"] == "0.5"
    assert body["values"]["w_p"] == "0.3"
    assert body["values"]["w_t"] == "0.2"


def test_the_form_is_prefilled_with_the_rules_of_the_ranking_not_the_ones_in_force(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca, d_sat="800")
    make_socio(db)
    calculate_ranking(client, boca)
    # Después del ranking el Admin ajusta los parámetros (HU-28): rige la versión 2.
    adjust_rules(client, boca, 1, d_sat="1500")

    body = client.get(SIMULATOR, headers=boca).json()

    assert body["ranking"]["rules_version"] == 1
    assert body["values"]["d_sat"] == "800"
    assert "(reglas versión 1)." in body["baseline_text"]


def test_each_parameter_comes_with_its_limits_and_the_sum_rule(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    calculate_ranking(client, boca)

    formula = client.get(SIMULATOR, headers=boca).json()["formula"]

    assert (formula["id"], formula["version"]) == ("scoring-model", 1)
    by_key = {p["key"]: p for p in formula["parameters"]}
    assert list(by_key) == PARAMETER_KEYS
    assert by_key["d_sat"] | {"description": None} == {
        "key": "d_sat",
        "symbol": "dsat",
        "name": "Distancia de saturación",
        "unit": "km",
        "description": None,
        "default": "1200",
        "minimum": "50",
        "maximum": "3000",
    }
    assert formula["constraints"] == [
        {
            "parameters": ["w_a", "w_p", "w_t"],
            "total": "1",
            "label": "Los pesos de asistencia, participación institucional y "
            "antigüedad y edad",
        }
    ]


def test_the_derived_value_b_is_shown_read_only_for_the_ranking_values(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca, d_sat="800")
    make_socio(db)
    calculate_ranking(client, boca)

    body = client.get(SIMULATOR, headers=boca).json()

    # b = 4,356 / 800 = 0,005445. No es un parámetro: no está en `values`.
    assert body["derived_values"] == [
        {
            "symbol": "b",
            "name": "Pendiente de la curva de distancia",
            "expression": "b = 4,356 / dsat",
            "value": "0.005445",
        }
    ]
    assert "b" not in body["values"]


def test_the_baseline_line_uses_the_buenos_aires_time_of_the_ranking(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_ranking(
        db,
        admin,
        RankingState.COMPLETED,
        calculated_at=datetime(2026, 10, 29, 14, 59, tzinfo=UTC),
        completed_at=datetime(2026, 10, 29, 15, 0, 3, tzinfo=UTC),
    )

    body = client.get(SIMULATOR, headers=boca).json()

    assert body["baseline_text"] == (
        "Comparado con el ranking calculado el 29/10/2026 12:00 (reglas versión 1)."
    )


def test_opening_the_simulator_changes_nothing_and_is_not_cached(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    calculate_ranking(client, boca)

    first = client.get(SIMULATOR, headers=boca)
    second = client.get(SIMULATOR, headers=boca)

    assert first.headers["cache-control"] == "no-store"
    assert first.json() == second.json()


def test_without_a_completed_ranking_there_is_nothing_to_compare_against(
    client: TestClient, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)

    response = client.get(SIMULATOR, headers=boca)

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "NO_BASELINE",
        "message": "Todavía no hay un ranking calculado, así que no hay con qué "
        "comparar. Calculá el ranking para poder simular.",
    }


# --- Unitarias -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("completed_at", "expected"),
    [
        (datetime(2026, 10, 29, 15, 0, 3, tzinfo=UTC), "29/10/2026 12:00"),
        # Pasada la medianoche UTC sigue siendo el día anterior en Buenos Aires.
        (datetime(2026, 11, 1, 2, 30, tzinfo=UTC), "31/10/2026 23:30"),
    ],
)
def test_baseline_text(completed_at: datetime, expected: str) -> None:
    assert baseline_text(completed_at, 3) == (
        f"Comparado con el ranking calculado el {expected} (reglas versión 3)."
    )


@pytest.mark.parametrize(
    ("d_sat", "b"),
    [("1200", "0.003630"), ("800", "0.005445"), ("700", "0.006223")],
)
def test_derived_b_is_rounded_for_display(d_sat: str, b: str) -> None:
    values = {p.key: p.default for p in SCORING_MODEL_V1.parameters}
    values["d_sat"] = Decimal(d_sat)

    assert derived_values(SCORING_MODEL_V1, values) == {"b": Decimal(b)}


def test_the_displayed_b_is_the_slope_the_engine_uses() -> None:
    assert distance_slope(Decimal(1200)) == Decimal("4.356") / Decimal(1200)

"""HU-29, escenario 23: el resultado, lado a lado con la situación actual.

"Given any result, When it is shown, Then it is side by side with the current situation
(before/after), labelled "Ranking actual" with its rules version and date, and "Simulación"
with the changed parameters; the equity analysis of HU-30 is shown on the same screen, computed
from the same hypothetical values; it is not a separate simulation."
Contrato: `docs/contrato-api-simulacion-reglas.md` §5.2 (`labels`, `derived_values`); SC-002.

El análisis de equidad (HU-30) todavía no está: cuando esté, va dentro de esta misma respuesta.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, User
from app.services import rules_simulation_service
from app.services.rules_simulation_service import baseline_text, labels
from tests.conftest import Outbox
from tests.hu25_helpers import DEFAULTS, adjust_rules, headers_for, publish_rules
from tests.hu29_helpers import CHANGED, SIMULATOR, make_varied_club, run_ranking

COMPLETED_AT = datetime(2026, 10, 29, 15, 0, 3, tzinfo=UTC)


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


@pytest.fixture
def ranking(db: Session, admin: User, boca: dict[str, str]) -> Ranking:
    make_varied_club(db)
    ranking = run_ranking(db, admin)
    ranking.completed_at = COMPLETED_AT
    db.flush()
    return ranking


def simulate(
    client: TestClient, headers: dict[str, str], values: dict[str, Any]
) -> Any:
    response = client.post(SIMULATOR, json={"values": values}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- Aceptación ----------------------------------------------------------------------------


def test_the_result_is_labelled_ranking_actual_and_simulacion(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, CHANGED)

    assert body["labels"] == {
        "before": "Ranking actual (reglas versión 1, 29/10/2026)",
        "after": "Simulación",
    }
    # "Simulación" va con los parámetros cambiados, con sus dos valores.
    assert [p["key"] for p in body["changed_parameters"]] == [
        "w_a",
        "w_p",
        "alpha_a",
        "d_sat",
        "b_max",
    ]
    assert all(p["before"] and p["after"] for p in body["changed_parameters"])


def test_every_figure_comes_before_and_after(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, CHANGED)

    assert set(body["summary"]) == {"before", "after", "difference"}
    assert set(body["saturation"]) == {"before", "after"}
    assert all({"before", "after"} <= set(b) for b in body["histogram"])
    assert all({"before", "after", "difference"} <= set(c) for c in body["components"])
    assert all({"before", "after"} <= set(d) for d in body["derived_values"])


def test_without_changes_the_result_is_also_side_by_side(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    # SC-002: el 100 % de los resultados, también el de `NO_CHANGES`.
    body = simulate(client, boca, DEFAULTS)

    assert body["status"] == "no_changes"
    assert body["labels"]["before"] == "Ranking actual (reglas versión 1, 29/10/2026)"
    assert body["labels"]["after"] == "Simulación"


def test_the_label_has_the_rules_version_of_the_ranking_not_the_one_in_force(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    adjust_rules(client, boca, 1, d_sat="800")

    body = simulate(client, boca, CHANGED)

    assert body["labels"]["before"] == "Ranking actual (reglas versión 1, 29/10/2026)"


def test_the_label_has_the_buenos_aires_date_of_the_baseline_line(
    client: TestClient, db: Session, boca: dict[str, str], ranking: Ranking
) -> None:
    # 02:30 UTC del 1/11 es todavía el 31/10 en Buenos Aires: la misma fecha de la línea.
    ranking.completed_at = datetime(2026, 11, 1, 2, 30, tzinfo=UTC)
    db.flush()

    body = simulate(client, boca, CHANGED)

    assert body["labels"]["before"] == "Ranking actual (reglas versión 1, 31/10/2026)"
    assert "31/10/2026" in body["baseline_text"]


def test_the_derived_values_come_before_and_after(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    # b = 4,356 / dsat: 1200 en el ranking, 800 en la simulación.
    body = simulate(client, boca, {**DEFAULTS, "d_sat": "800"})

    assert body["derived_values"] == [
        {"symbol": "b", "before": "0.00363", "after": "0.005445"}
    ]


def test_a_derived_value_not_touched_is_the_same_before_and_after(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, {**DEFAULTS, "alpha_a": "0.4"})

    assert body["derived_values"] == [
        {"symbol": "b", "before": "0.00363", "after": "0.00363"}
    ]


def test_a_derived_value_without_a_known_calculation_comes_empty(
    client: TestClient,
    boca: dict[str, str],
    ranking: Ranking,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Una fórmula sin cálculo conocido para su derivado: se muestra solo la expresión.
    monkeypatch.setattr(rules_simulation_service, "derived_values", lambda *_: {})

    body = simulate(client, boca, CHANGED)

    assert body["derived_values"] == [{"symbol": "b", "before": None, "after": None}]


# --- Unitarias -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("completed_at", "day"),
    [
        (COMPLETED_AT, "29/10/2026"),
        (datetime(2026, 11, 1, 2, 30, tzinfo=UTC), "31/10/2026"),
        (datetime(2026, 11, 1, 3, 0, tzinfo=UTC), "01/11/2026"),
    ],
)
def test_labels(completed_at: datetime, day: str) -> None:
    assert labels(completed_at, 7).model_dump() == {
        "before": f"Ranking actual (reglas versión 7, {day})",
        "after": "Simulación",
    }
    # El mismo día que la línea de la base.
    assert day in baseline_text(completed_at, 7)

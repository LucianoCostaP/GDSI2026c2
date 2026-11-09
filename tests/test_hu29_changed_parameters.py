"""HU-29, escenario 17: parámetros cambiados y factores.

"Given a simulation, When it is shown, Then it lists the changed parameters: those whose
hypothetical value differs from the value of the ranking's rules version, with both values.
Parameters are grouped in four factors: pillar weights (`wA`, `wP`, `wT`, always together
because they must add up to 1.00), distance weight inside attendance (`αA`), distance
inflection (`dsat`), and other parameters (`Pinst_max`, `αT`, `Tref`, `Eref`, `γ`, `Bmax`,
`Tmax`, `tcarencia`)." Contrato: `docs/contrato-api-simulacion-reglas.md` §5.2 y §5.4.

La lista completa con los cuatro factores se prueba también en `test_hu29_recalculation.py`.
"""

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, User
from app.scoring.formatting import decimal_to_str
from tests.conftest import Outbox
from tests.hu25_helpers import DEFAULTS, adjust_rules, headers_for, publish_rules
from tests.hu29_helpers import SIMULATOR, make_varied_club, run_ranking


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


@pytest.fixture
def ranking(db: Session, admin: User, boca: dict[str, str]) -> Ranking:
    make_varied_club(db)
    return run_ranking(db, admin)


def simulate(
    client: TestClient, headers: dict[str, str], values: dict[str, Any]
) -> Any:
    response = client.post(SIMULATOR, json={"values": values}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def canonical(value: str) -> str:
    """Como viajan los valores: sin ceros de más ("1.0" es "1")."""
    return decimal_to_str(Decimal(value))


def changed(body: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    return [
        (p["key"], p["factor"], p["before"], p["after"])
        for p in body["changed_parameters"]
    ]


# --- Aceptación ----------------------------------------------------------------------------


def test_the_pillar_weights_are_one_factor_and_only_the_changed_ones_are_listed(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    # wP queda igual: no aparece, pero wA y wT forman un solo factor.
    body = simulate(client, boca, {**DEFAULTS, "w_a": "0.7", "w_t": "0.1"})

    assert changed(body) == [
        ("w_a", "pillar_weights", "0.6", "0.7"),
        ("w_t", "pillar_weights", "0.2", "0.1"),
    ]
    assert body["factors_changed"] == ["pillar_weights"]


@pytest.mark.parametrize(
    ("values", "factor"),
    [
        ({"alpha_a": "0.3"}, "alpha_a"),
        ({"d_sat": "800"}, "d_sat"),
        ({"p_inst_max": "80", "alpha_t": "0.5", "t_ref": "40"}, "other"),
        ({"e_ref": "70", "gamma": "0.9", "b_max": "10"}, "other"),
        ({"t_max": "200", "t_carencia": "180"}, "other"),
    ],
    ids=["alpha-a", "d-sat", "other-1", "other-2", "other-3"],
)
def test_each_parameter_is_listed_with_its_factor(
    client: TestClient,
    boca: dict[str, str],
    ranking: Ranking,
    values: dict[str, str],
    factor: str,
) -> None:
    body = simulate(client, boca, {**DEFAULTS, **values})

    assert changed(body) == [
        (key, factor, canonical(DEFAULTS[key]), value) for key, value in values.items()
    ]
    assert body["factors_changed"] == [factor]


def test_the_list_keeps_the_order_of_the_formula_not_the_one_of_the_request(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    values = {"t_carencia": "180", "d_sat": "800", **DEFAULTS}
    values.update(t_carencia="180", d_sat="800", w_p="0.3", w_a="0.5")

    body = simulate(client, boca, values)

    assert [p["key"] for p in body["changed_parameters"]] == [
        "w_a",
        "w_p",
        "d_sat",
        "t_carencia",
    ]
    assert body["factors_changed"] == ["pillar_weights", "d_sat", "other"]


def test_the_previous_value_is_the_one_of_the_ranking_not_the_one_in_force(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    # Después del ranking, dsat vigente pasa a 800; el ranking se calculó con 1200.
    adjust_rules(client, boca, 1, d_sat="800")

    body = simulate(client, boca, {**DEFAULTS, "d_sat": "800"})

    assert changed(body) == [("d_sat", "d_sat", "1200", "800")]


def test_both_values_travel_without_trailing_zeros(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, {**DEFAULTS, "alpha_a": "0.250"})

    assert changed(body) == [("alpha_a", "alpha_a", "0.2", "0.25")]

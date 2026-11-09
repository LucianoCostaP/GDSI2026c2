"""HU-29, escenario 19: el resto (otros parámetros e interacciones).

"Given the isolated simulations of scenario 18, When they are shown, Then next to them a row
"Resto: otros parámetros e interacciones" shows the mean change of the total of the full
simulation minus the sum of the isolated ones, and lists the changed parameters that are not
isolated (the factor "other parameters"). The effects of the factors are not additive in
general, and the screen says so." Contrato: `docs/contrato-api-simulacion-reglas.md` §6.
"""

from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, RankingEntry, User
from app.scoring.rules_simulation import FactorEffect, Movement, remainder_change
from tests.conftest import Outbox
from tests.hu25_helpers import (
    DEFAULTS,
    adjust_rules,
    entries_of,
    headers_for,
    publish_rules,
)
from tests.hu29_helpers import (
    ISOLATED,
    SIMULATOR,
    SPREAD,
    make_saturation_club,
    run_ranking,
)

BREAKDOWN = f"{SIMULATOR}/breakdown"
LABEL = "Resto: otros parámetros e interacciones"
NOTE = "Los efectos de cada grupo no se suman: al combinarlos interactúan."


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


@pytest.fixture
def ranking(db: Session, admin: User, boca: dict[str, str]) -> Ranking:
    make_saturation_club(db)
    return run_ranking(db, admin)


def breakdown(
    client: TestClient, headers: dict[str, str], ranking_id: int, values: dict[str, Any]
) -> Any:
    response = client.post(
        BREAKDOWN, json={"ranking_id": ranking_id, "values": values}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def mean_change(base: list[RankingEntry], official: list[RankingEntry]) -> Fraction:
    """Cambio exacto del total medio entre dos rankings reales, contado a mano."""
    by_socio = {e.socio_id: e.total for e in official}
    return Fraction(sum(by_socio[e.socio_id] - e.total for e in base)) / len(base)


def shown(value: Fraction) -> str:
    exact = Decimal(value.numerator) / Decimal(value.denominator)
    return str(exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) + 0)


def official_change(
    client: TestClient,
    db: Session,
    admin: User,
    headers: dict[str, str],
    version: int,
    base: list[RankingEntry],
    values: dict[str, str],
) -> Fraction:
    """El cambio del total medio con un cálculo real de HU-25 con esos valores."""
    adjust_rules(client, headers, version, **values)
    return mean_change(base, entries_of(db, run_ranking(db, admin)))


# --- Aceptación ----------------------------------------------------------------------------


def test_the_remainder_is_the_full_change_minus_the_isolated_ones(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
) -> None:
    body = breakdown(client, boca, ranking.id, SPREAD)
    base = entries_of(db, ranking)
    isolated = [
        official_change(client, db, admin, boca, version, base, values)
        for version, values in enumerate(ISOLATED.values(), start=1)
    ]
    full = official_change(client, db, admin, boca, 4, base, SPREAD)

    assert body["remainder"] == {
        "label": LABEL,
        "mean_total_change": shown(full - sum(isolated, Fraction(0))),
        "parameters": ["b_max"],
    }
    assert body["non_additive_note"] == NOTE
    # Con Bmax cambiado el resto no es 0: si no, el test no distinguiría la resta.
    assert body["remainder"]["mean_total_change"] != "0.00"


def test_the_remainder_lists_every_other_parameter_changed(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    values = {**SPREAD, "t_carencia": "180", "gamma": "0.9", "p_inst_max": "80"}

    body = breakdown(client, boca, ranking.id, values)

    # En el orden de la fórmula, no en el del pedido.
    assert body["remainder"]["parameters"] == [
        "p_inst_max",
        "gamma",
        "b_max",
        "t_carencia",
    ]


def test_without_other_parameters_the_remainder_is_only_interaction(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
) -> None:
    # Solo αA y dsat: el resto es lo que suman al combinarse, sin otros parámetros.
    values = {**DEFAULTS, **ISOLATED["alpha_a"], **ISOLATED["d_sat"]}

    body = breakdown(client, boca, ranking.id, values)
    base = entries_of(db, ranking)
    alpha = official_change(client, db, admin, boca, 1, base, ISOLATED["alpha_a"])
    d_sat = official_change(client, db, admin, boca, 2, base, ISOLATED["d_sat"])
    full = official_change(
        client, db, admin, boca, 3, base, {**ISOLATED["alpha_a"], **ISOLATED["d_sat"]}
    )

    assert body["remainder"] == {
        "label": LABEL,
        "mean_total_change": shown(full - alpha - d_sat),
        "parameters": [],
    }
    # Los efectos no se suman: la interacción existe.
    assert full != alpha + d_sat
    assert body["non_additive_note"] == NOTE


def test_the_isolated_ones_plus_the_remainder_give_the_change_of_the_main_result(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = breakdown(client, boca, ranking.id, SPREAD)
    main = client.post(SIMULATOR, json={"values": SPREAD}, headers=boca).json()

    parts = [Decimal(f["mean_total_change"]) for f in body["factors"]]
    parts.append(Decimal(body["remainder"]["mean_total_change"]))
    total = {c["key"]: c for c in main["components"]}["total"]
    # Mostrados con 2 decimales, cada redondeo puede correr la suma 0,005.
    assert abs(sum(parts) - Decimal(total["difference"])) <= Decimal("0.02")


# --- Unitarias -----------------------------------------------------------------------------


def effect(change: Fraction) -> FactorEffect:
    return FactorEffect("alpha_a", (), change, Movement(0, 0, 0, Decimal(0), 1, 0, 0))


def test_the_remainder_uses_the_exact_values() -> None:
    # 1/3 − (1/6 + 1/6) = 0 exacto; redondeados (0,33 − 0,17 − 0,17) darían −0,01.
    assert remainder_change(Fraction(1, 3), [effect(Fraction(1, 6))] * 2) == 0


def test_the_remainder_can_be_negative() -> None:
    assert remainder_change(Fraction(1), [effect(Fraction(3, 2))]) == Fraction(-1, 2)


def test_without_isolated_effects_the_remainder_is_the_full_change() -> None:
    assert remainder_change(Fraction(7, 3), []) == Fraction(7, 3)

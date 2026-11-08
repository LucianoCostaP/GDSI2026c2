"""HU-29, escenario 15: alertas de saturación y de concentración.

"Given the simulation puts at the cap at least as many Socios as the relevant movement
threshold and more than the ranking has, When it is shown, Then the saturation alert
`SATURATION_ALERT` appears, stating the number of Socios at 100 now and in the simulation and
that their order would be decided by seniority and age. Given the standard deviation of the
simulation is 80 % or less of the ranking's (and the ranking's is not 0), Then the flatness
alert `FLATNESS_ALERT` appears with the percentage of drop. Both can appear at the same time;
neither blocks anything." Contrato: `docs/contrato-api-simulacion-reglas.md` §5.2.
"""

import statistics
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, User
from app.scoring.distribution import (
    FlatnessAlert,
    Saturation,
    SaturationAlert,
    flatness_alert,
    saturation_alert,
)
from app.services import rules_simulation_service
from tests.conftest import Outbox
from tests.hu25_helpers import (
    DEFAULTS,
    adjust_rules,
    entries_of,
    headers_for,
    publish_rules,
)
from tests.hu29_helpers import (
    CHANGED,
    FLATTER,
    SIMULATOR,
    TO_THE_CAP,
    make_saturation_club,
    run_ranking,
)


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


@pytest.fixture
def ranking(db: Session, admin: User, boca: dict[str, str]) -> Ranking:
    """11 socios (m = 1); hoy ninguno llega a 100."""
    make_saturation_club(db)
    return run_ranking(db, admin)


def simulate(
    client: TestClient, headers: dict[str, str], values: dict[str, Any]
) -> Any:
    response = client.post(SIMULATOR, json={"values": values}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def codes(body: dict[str, Any]) -> list[str]:
    return [alert["code"] for alert in body["alerts"]]


# --- Aceptación: saturación ----------------------------------------------------------------


def test_the_saturation_alert_says_how_many_reach_the_cap_now_and_simulated(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, TO_THE_CAP)

    assert body["saturation"]["after"]["at_cap"] == 1
    assert body["alerts"] == [
        {
            "code": "SATURATION_ALERT",
            "text": (
                "Con estos valores 1 socios llegarían al tope de 100 (hoy 0). "
                "Entre ellos el orden lo definirían la antigüedad y la edad."
            ),
            "at_cap_after": 1,
            "at_cap_before": 0,
        }
    ]


def test_no_saturation_alert_if_the_ranking_already_had_as_many_at_the_cap(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
) -> None:
    # Un ranking calculado con esas reglas ya tiene al socio estrella en 100.
    adjust_rules(client, boca, 1, **TO_THE_CAP)
    run_ranking(db, admin)

    body = simulate(client, boca, TO_THE_CAP)

    assert body["saturation"]["before"]["at_cap"] == 1
    assert "SATURATION_ALERT" not in codes(body)


# --- Aceptación: concentración -------------------------------------------------------------


def test_the_flatness_alert_says_how_much_the_dispersion_drops(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
) -> None:
    body = simulate(client, boca, FLATTER)
    # La verdad: un cálculo real de HU-25 con esas reglas (escenario 8).
    adjust_rules(client, boca, 1, **FLATTER)
    official = run_ranking(db, admin)

    sigma_before = statistics.pstdev([e.total for e in entries_of(db, ranking)])
    sigma_after = statistics.pstdev([e.total for e in entries_of(db, official)])
    assert sigma_after <= Decimal("0.8") * sigma_before
    drop = (100 * (1 - sigma_after / sigma_before)).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_UP
    )
    assert body["alerts"] == [
        {
            "code": "FLATNESS_ALERT",
            "text": (
                "Con estos valores los puntajes se concentran: "
                f"la dispersión baja un {str(drop).replace('.', ',')} %."
            ),
            "drop_percent": str(drop),
        }
    ]


def test_a_wider_spread_gives_no_flatness_alert(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, CHANGED)

    assert Decimal(body["summary"]["difference"]["std_dev"]) > 0
    assert "FLATNESS_ALERT" not in codes(body)


# --- Aceptación: las dos, ninguna, y nada se bloquea ---------------------------------------


def test_both_alerts_can_appear_together_saturation_first(
    client: TestClient,
    boca: dict[str, str],
    ranking: Ranking,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rules_simulation_service,
        "flatness_alert",
        lambda *_: FlatnessAlert(drop_percent=Decimal("23.45")),
    )

    body = simulate(client, boca, TO_THE_CAP)

    assert codes(body) == ["SATURATION_ALERT", "FLATNESS_ALERT"]
    assert body["alerts"][1]["drop_percent"] == "23.5"
    assert body["alerts"][1]["text"].endswith("la dispersión baja un 23,5 %.")


def test_with_the_values_of_the_ranking_there_are_no_alerts(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, DEFAULTS)

    assert body["status"] == "no_changes"
    assert body["alerts"] == []


def test_alerts_do_not_block_the_result(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, TO_THE_CAP)

    assert body["alerts"]
    assert body["status"] == "changed"
    assert len(body["histogram"]) == 20 and len(body["components"]) == 7


# --- Unitarias: saturación -----------------------------------------------------------------


def at_cap(n: int) -> Saturation:
    return Saturation(at_cap=n, needs_cap_adjustment=n, tied=0, largest_tie=0)


@pytest.mark.parametrize(
    ("before", "after", "m", "alert"),
    [
        (0, 3, 3, True),  # justo m
        (0, 2, 3, False),  # menos que m
        (3, 3, 3, False),  # no más que el ranking
        (5, 4, 3, False),  # menos que el ranking
        (3, 4, 3, True),
        (0, 1, 1, True),
        (0, 0, 1, False),
    ],
)
def test_the_saturation_alert_needs_m_at_the_cap_and_more_than_the_ranking(
    before: int, after: int, m: int, alert: bool
) -> None:
    result = saturation_alert(at_cap(before), at_cap(after), m)

    assert result == (SaturationAlert(before, after) if alert else None)


# --- Unitarias: concentración --------------------------------------------------------------


def amounts(*values: str) -> list[Decimal]:
    return [Decimal(v) for v in values]


def test_a_deviation_of_exactly_80_percent_is_flat() -> None:
    # σ ranking = 5; σ simulación = 4: la razón es exactamente 0,8.
    alert = flatness_alert(amounts("0", "10"), amounts("1", "9"))

    assert alert == FlatnessAlert(drop_percent=Decimal(20))


def test_a_deviation_just_above_80_percent_is_not_flat() -> None:
    # σ = 4,01 > 4: no alcanza, aunque redondeado se parezca.
    assert flatness_alert(amounts("0", "10"), amounts("0.99", "9.01")) is None


def test_the_drop_is_exact() -> None:
    # σ ranking = 10; σ simulación = 1: baja 90 %.
    alert = flatness_alert(amounts("0", "20"), amounts("9", "11"))

    assert alert == FlatnessAlert(drop_percent=Decimal(90))


def test_no_flatness_alert_when_the_ranking_has_no_dispersion() -> None:
    assert flatness_alert(amounts("50", "50"), amounts("50", "50")) is None
    assert flatness_alert(amounts("50", "50"), amounts("40", "60")) is None


def test_all_equal_in_the_simulation_is_a_drop_of_100_percent() -> None:
    alert = flatness_alert(amounts("0", "10"), amounts("5", "5"))

    assert alert == FlatnessAlert(drop_percent=Decimal(100))


def test_both_situations_need_the_same_socios() -> None:
    with pytest.raises(ValueError):
        flatness_alert(amounts("0", "10"), amounts("5"))

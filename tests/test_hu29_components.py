"""HU-29, escenario 16: cambio por componente.

"Given a simulation result, When it is shown, Then it includes, for each component stored per
Socio (`attendance_frequency`, `attendance_distance`, `institutional`, `seniority_age`,
`new_member_bonus`, `cap_adjustment`) and for the total, the mean in the ranking, the mean in
the simulation and the change, over all Socios of the ranking, with the labels of HU-16. The
changes of the six components add up exactly to the change of the mean total."
Contrato: `docs/contrato-api-simulacion-reglas.md` §5.2, §5.4 y §9 punto 3.
"""

from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, RankingEntry, User
from app.scoring.components import COMPONENT_KEYS
from app.scoring.distribution import (
    ComponentChange,
    component_changes,
    fraction_to_decimal,
)
from app.scoring.engine import ScoringParameters
from app.scoring.rules_simulation import simulate_entries
from app.services.rules_simulation_service import stored_entries
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
    SIMULATOR,
    TO_THE_CAP,
    make_saturation_club,
    run_ranking,
)

LABELS = [
    ("attendance_frequency", "asistencia – frecuencia"),
    ("attendance_distance", "asistencia – distancia"),
    ("institutional", "participación institucional"),
    ("seniority_age", "antigüedad y edad"),
    ("new_member_bonus", "bonus nuevo socio"),
    ("cap_adjustment", "ajuste por tope"),
    ("total", "total"),
]


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


def means(entries: list[RankingEntry]) -> dict[str, Decimal]:
    """Promedios esperados, hechos a mano sobre las entradas de un ranking real."""
    n = len(entries)
    keys = [*COMPONENT_KEYS, "total"]
    return {key: Decimal(sum(getattr(e, key) for e in entries)) / n for key in keys}


def shown(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) + 0)


# --- Aceptación ----------------------------------------------------------------------------


@pytest.mark.parametrize("values", [CHANGED, TO_THE_CAP], ids=["changed", "to-the-cap"])
def test_the_result_has_the_mean_of_each_component_and_of_the_total(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
    values: dict[str, str],
) -> None:
    body = simulate(client, boca, values)
    # La simulación da lo mismo que un cálculo real de HU-25 con esas reglas (escenario 8).
    adjust_rules(client, boca, 1, **values)
    official = run_ranking(db, admin)

    before, after = means(entries_of(db, ranking)), means(entries_of(db, official))
    assert body["components"] == [
        {
            "key": key,
            "label": label,
            "before": shown(before[key]),
            "after": shown(after[key]),
            "difference": shown(after[key] - before[key]),
        }
        for key, label in LABELS
    ]


def test_the_cap_adjustment_shows_up_when_someone_passes_100(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, TO_THE_CAP)

    cap = {c["key"]: c for c in body["components"]}["cap_adjustment"]
    # Un socio de 11 con un ajuste de −15,27: el promedio es −1,388…
    assert (cap["before"], cap["after"], cap["difference"]) == (
        "0.00",
        "-1.39",
        "-1.39",
    )


def test_the_six_changes_add_up_exactly_to_the_change_of_the_total(
    db: Session, ranking: Ranking
) -> None:
    before = stored_entries(db, ranking.id)
    after = simulate_entries(before, ScoringParameters.from_values(TO_THE_CAP))

    changes = component_changes(
        COMPONENT_KEYS,
        ([e.components for e in before], [e.total for e in before]),
        ([e.components for e in after], [e.total for e in after]),
    )

    *six, total = changes
    assert total.key == "total"
    assert sum(c.difference for c in six) == total.difference
    assert total.difference != 0


def test_with_the_values_of_the_ranking_every_change_is_0(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, DEFAULTS)

    assert body["status"] == "no_changes"
    assert [(c["key"], c["label"]) for c in body["components"]] == LABELS
    for component in body["components"]:
        assert component["before"] == component["after"]
        assert component["difference"] == "0.00"


# --- Unitarias -----------------------------------------------------------------------------


def socio(**values: str) -> dict[str, Decimal]:
    components = {key: Decimal("0.00") for key in COMPONENT_KEYS}
    components.update({key: Decimal(v) for key, v in values.items()})
    return components


def situation(
    *socios: dict[str, Decimal],
) -> tuple[list[dict[str, Decimal]], list[Decimal]]:
    return list(socios), [sum(s.values(), Decimal(0)) for s in socios]


def test_means_are_exact_fractions_over_all_socios() -> None:
    before = situation(socio(institutional="10"), socio(), socio())
    after = situation(socio(institutional="10.01"), socio(), socio())

    changes = component_changes(COMPONENT_KEYS, before, after)

    by_key = {c.key: c for c in changes}
    assert by_key["institutional"] == ComponentChange(
        "institutional", Fraction(10, 3), Fraction(1001, 300)
    )
    assert by_key["institutional"].difference == Fraction(1, 300)
    assert by_key["total"].difference == Fraction(1, 300)


def test_the_sum_is_exact_even_when_each_mean_repeats_forever() -> None:
    # Siete socios: cada promedio es periódico; con fracciones la suma no pierde nada.
    before = situation(*(socio(seniority_age="7.29") for _ in range(7)))
    after = situation(
        *(
            socio(attendance_frequency=f"{i}.01", new_member_bonus="0.03")
            for i in range(7)
        )
    )

    *six, total = component_changes(COMPONENT_KEYS, before, after)

    assert sum(c.difference for c in six) == total.difference


def test_the_total_comes_last_and_components_keep_their_order() -> None:
    changes = component_changes(COMPONENT_KEYS, situation(socio()), situation(socio()))

    assert [c.key for c in changes] == [key for key, _ in LABELS]


def test_both_situations_need_the_same_socios() -> None:
    with pytest.raises(ValueError):
        component_changes(COMPONENT_KEYS, situation(socio()), situation())
    with pytest.raises(ValueError):
        component_changes(COMPONENT_KEYS, situation(), situation())


def test_fractions_are_turned_into_decimals_for_display() -> None:
    assert fraction_to_decimal(Fraction(-1527, 1000)) == Decimal("-1.527")
    assert str(fraction_to_decimal(Fraction(1, 3)))[:12] == "0.3333333333"

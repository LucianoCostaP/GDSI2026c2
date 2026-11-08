"""HU-29, escenario 18: efecto de cada factor por separado.

"Given two or more factors changed, When the result is shown, Then, besides the full
simulation, one additional simulation is run for each changed factor among pillar weights, `αA`
and `dsat`, applying only that factor's hypothetical values over the values of the ranking's
rules version. Each one reports the mean change of the total, the Socios that go up and go
down, and the mean absolute change of position; they are ordered from the largest to the
smallest mean absolute change of position (ties: pillar weights, `αA`, `dsat`), and the first
is flagged as the factor that weighs most." Contrato: `docs/contrato-api-simulacion-reglas.md`
§5.2 (`breakdown`), §6 y §9 puntos 1, 2 y 6.
"""

import uuid
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Ranking, RankingEntry, RankingState, RulesVersion, User
from app.scoring.catalog import get_descriptor
from app.scoring.engine import ScoringParameters
from app.scoring.rules_simulation import (
    FactorEffect,
    Movement,
    SimulatedEntry,
    StoredEntry,
    factors_to_isolate,
    isolated_values,
    mean_total_change,
    rank_effects,
)
from app.scoring.validation import validate_values
from app.services.rules_simulation_service import (
    BASELINE_NOT_FOUND_MESSAGE,
    EMPTY_RANKING_MESSAGE,
)
from tests.conftest import RIVER_ID, MakeAdmin, MakeMember, Outbox, bearer, member_token
from tests.hu25_helpers import (
    DEFAULTS,
    adjust_rules,
    entries_of,
    headers_for,
    make_ranking,
    make_socio,
    publish_rules,
)
from tests.hu29_helpers import CHANGED, SIMULATOR, make_saturation_club, run_ranking

BREAKDOWN = f"{SIMULATOR}/breakdown"
LABELS = {
    "pillar_weights": "Pesos de los pilares",
    "alpha_a": "Peso de la distancia (αA)",
    "d_sat": "Punto de inflexión de la distancia (dsat)",
}
# Cambia los cuatro factores; cada uno mueve el ranking distinto, y en un orden que no es el
# del desempate: αA (1,5 posiciones de cambio medio), dsat (0,4) y los pesos (0,2).
SPREAD = {
    **DEFAULTS,
    "w_a": "0.5",
    "w_p": "0.3",
    "alpha_a": "1",
    "d_sat": "100",
    "b_max": "20",
}
# Cada factor solo, sobre los valores del ranking.
ISOLATED = {
    "pillar_weights": {"w_a": "0.5", "w_p": "0.3", "w_t": "0.2"},
    "alpha_a": {"alpha_a": "1"},
    "d_sat": {"d_sat": "100"},
}
PARAMETERS = {
    "pillar_weights": ["w_a", "w_p"],
    "alpha_a": ["alpha_a"],
    "d_sat": ["d_sat"],
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


def post_breakdown(
    client: TestClient,
    headers: dict[str, str],
    ranking_id: int,
    values: dict[str, Any],
) -> Any:
    return client.post(
        BREAKDOWN, json={"ranking_id": ranking_id, "values": values}, headers=headers
    )


def breakdown(
    client: TestClient,
    headers: dict[str, str],
    ranking_id: int,
    values: dict[str, Any],
) -> Any:
    response = post_breakdown(client, headers, ranking_id, values)
    assert response.status_code == 200, response.text
    return response.json()


def shown(value: Fraction | Decimal, places: str) -> str:
    exact = Decimal(value.numerator) / Decimal(value.denominator)
    return str(exact.quantize(Decimal(places), rounding=ROUND_HALF_UP) + 0)


def effect_of(base: list[RankingEntry], official: list[RankingEntry]) -> dict[str, Any]:
    """Lo esperado, contado a mano entre dos rankings reales de HU-25."""
    by_socio = {e.socio_id: e for e in official}
    changes = [e.position - by_socio[e.socio_id].position for e in base]
    total_change = Fraction(sum(by_socio[e.socio_id].total - e.total for e in base))
    abs_change = Fraction(sum(abs(c) for c in changes), len(base))
    return {
        "mean_total_change": shown(total_change / len(base), "0.01"),
        "up": sum(1 for c in changes if c > 0),
        "down": sum(1 for c in changes if c < 0),
        "mean_abs_position_change": shown(abs_change, "0.1"),
        "_order": abs_change,
    }


# --- Aceptación ----------------------------------------------------------------------------


def test_each_changed_factor_is_simulated_alone_like_hu25_would_calculate_it(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
) -> None:
    body = breakdown(client, boca, ranking.id, SPREAD)
    # La verdad: un cálculo real de HU-25 con solo los valores de cada factor (escenario 22).
    base = entries_of(db, ranking)
    expected = []
    for version, (factor, values) in enumerate(ISOLATED.items(), start=1):
        adjust_rules(client, boca, version, **values)
        official = entries_of(db, run_ranking(db, admin))
        expected.append({"factor": factor, **effect_of(base, official)})

    # De mayor a menor cambio de posición; el orden de la lista ya es el del desempate.
    expected.sort(key=lambda e: -e["_order"])
    assert body["status"] == "available"
    assert (body["code"], body["message"]) == (None, None)
    assert body["ranking_id"] == ranking.id
    assert body["factors"] == [
        {
            "factor": e["factor"],
            "label": LABELS[e["factor"]],
            "parameters": PARAMETERS[e["factor"]],
            "mean_total_change": e["mean_total_change"],
            "up": e["up"],
            "down": e["down"],
            "mean_abs_position_change": e["mean_abs_position_change"],
            "weighs_most": i == 0,
            "weighs_most_text": "Es el que más mueve el ranking." if i == 0 else None,
        }
        for i, e in enumerate(expected)
    ]
    # Si el orden fuera el del desempate, el test no probaría el ordenamiento.
    assert [e["factor"] for e in expected] == ["alpha_a", "d_sat", "pillar_weights"]


def test_the_main_result_says_the_breakdown_is_pending(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    response = client.post(SIMULATOR, json={"values": CHANGED}, headers=boca)

    assert response.status_code == 200, response.text
    assert response.json()["breakdown"] == {
        "status": "pending",
        "code": None,
        "message": "Calculando el efecto de cada parámetro…",
    }


def test_other_parameters_count_as_a_factor_but_are_never_simulated_alone(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    # Pesos + Bmax: dos factores, una sola simulación aislada (la de los pesos).
    values = {**DEFAULTS, **ISOLATED["pillar_weights"], "b_max": "20"}

    main = client.post(SIMULATOR, json={"values": values}, headers=boca).json()
    body = breakdown(client, boca, ranking.id, values)

    assert main["breakdown"]["status"] == "pending"
    assert [f["factor"] for f in body["factors"]] == ["pillar_weights"]
    assert body["factors"][0]["parameters"] == ["w_a", "w_p"]
    assert body["factors"][0]["weighs_most"] is True


def test_each_factor_is_applied_over_the_rules_of_the_ranking_not_the_ones_in_force(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    before = breakdown(client, boca, ranking.id, CHANGED)
    # Otras reglas vigentes después del ranking: el desglose no las usa.
    adjust_rules(client, boca, 1, gamma="0.5", t_ref="20")

    after = breakdown(client, boca, ranking.id, CHANGED)

    assert after == before


def test_the_breakdown_uses_the_ranking_of_the_main_result(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
) -> None:
    expected = breakdown(client, boca, ranking.id, CHANGED)
    # Se completa otro ranking, con un socio más: el desglose sigue sobre el primero.
    make_socio(db, distancia_km=Decimal("450.00"))
    newer = run_ranking(db, admin)

    body = breakdown(client, boca, ranking.id, CHANGED)

    assert body == expected
    assert breakdown(client, boca, newer.id, CHANGED)["ranking_id"] == newer.id


def test_the_breakdown_modifies_no_real_data(
    client: TestClient, db: Session, boca: dict[str, str], ranking: Ranking
) -> None:
    def state() -> tuple[Any, ...]:
        return (
            db.scalar(select(func.count()).select_from(Ranking)),
            db.scalar(select(func.count()).select_from(RulesVersion)),
            sorted((e.socio_id, e.position, e.total) for e in entries_of(db, ranking)),
        )

    snapshot = state()

    response = post_breakdown(client, boca, ranking.id, CHANGED)

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    db.expire_all()
    assert state() == snapshot


# --- Aceptación: rechazos ------------------------------------------------------------------


def test_a_ranking_that_does_not_exist_is_not_found(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    response = post_breakdown(client, boca, ranking.id + 1000, CHANGED)

    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "BASELINE_NOT_FOUND", "message": BASELINE_NOT_FOUND_MESSAGE}
    }
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    ("state", "club_id"),
    [
        (RankingState.COMPLETED, RIVER_ID),
        (RankingState.RUNNING, None),
        (RankingState.FAILED, None),
    ],
    ids=["other-club", "running", "failed"],
)
def test_only_a_completed_ranking_of_the_club_is_found(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
    state: RankingState,
    club_id: uuid.UUID | None,
) -> None:
    other = make_ranking(db, admin, state, **({"club_id": club_id} if club_id else {}))

    response = post_breakdown(client, boca, other.id, CHANGED)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BASELINE_NOT_FOUND"


def test_a_ranking_without_socios_is_rejected_before_validating(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    empty = make_ranking(db, admin, RankingState.COMPLETED)

    response = post_breakdown(client, boca, empty.id, {"w_a": "no"})

    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "EMPTY_RANKING", "message": EMPTY_RANKING_MESSAGE}
    }


def test_invalid_values_are_rejected_like_the_main_result(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    values = {**CHANGED, "w_a": "0.9", "d_sat": "1"}

    response = post_breakdown(client, boca, ranking.id, values)
    main = client.post(SIMULATOR, json={"values": values}, headers=boca)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_VALUES"
    assert response.json() == main.json()


def test_a_member_is_forbidden(
    client: TestClient,
    outbox: Outbox,
    make_member: MakeMember,
    ranking: Ranking,
) -> None:
    headers = bearer(member_token(client, outbox, make_member(activated=True)))

    response = post_breakdown(client, headers, ranking.id, CHANGED)

    assert (response.status_code, response.json()) == (403, {"detail": "FORBIDDEN"})


def test_an_admin_without_club_is_rejected(
    client: TestClient, outbox: Outbox, make_admin: MakeAdmin, ranking: Ranking
) -> None:
    headers = headers_for(client, outbox, make_admin(None))

    response = post_breakdown(client, headers, ranking.id, CHANGED)

    assert response.status_code == 403
    assert response.json() == {"detail": "ADMIN_WITHOUT_CLUB"}


def test_an_unauthenticated_request_is_rejected(
    client: TestClient, ranking: Ranking
) -> None:
    response = post_breakdown(client, {}, ranking.id, CHANGED)

    assert response.status_code == 401
    assert response.json() == {"detail": "NOT_AUTHENTICATED"}


def test_the_ranking_of_another_club_is_not_found_for_its_admin(
    client: TestClient, outbox: Outbox, make_admin: MakeAdmin, ranking: Ranking
) -> None:
    river = headers_for(client, outbox, make_admin(RIVER_ID))

    response = post_breakdown(client, river, ranking.id, CHANGED)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "BASELINE_NOT_FOUND"


# --- Sin desglose: un solo factor o ninguno ------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [ISOLATED["pillar_weights"], {"d_sat": "600"}, {"b_max": "20", "gamma": "0.9"}],
    ids=["pillar-weights", "d-sat", "other"],
)
def test_with_a_single_factor_no_isolated_simulation_is_run(
    client: TestClient,
    boca: dict[str, str],
    ranking: Ranking,
    values: dict[str, str],
) -> None:
    single = {**DEFAULTS, **values}
    message = (
        "Cambiaste un solo grupo de parámetros: su efecto es el del resultado total."
    )

    main = client.post(SIMULATOR, json={"values": single}, headers=boca).json()
    body = breakdown(client, boca, ranking.id, single)

    assert main["breakdown"] == {
        "status": "single_factor",
        "code": "SINGLE_FACTOR",
        "message": message,
    }
    assert body == {
        "ranking_id": ranking.id,
        "status": "single_factor",
        "code": "SINGLE_FACTOR",
        "message": message,
        "factors": [],
    }


def test_without_changes_there_is_no_breakdown(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    main = client.post(SIMULATOR, json={"values": DEFAULTS}, headers=boca).json()
    body = breakdown(client, boca, ranking.id, DEFAULTS)

    assert main["breakdown"] == {"status": "no_changes", "code": None, "message": None}
    assert (body["status"], body["code"], body["factors"]) == ("no_changes", None, [])


# --- Unitarias -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("factors", "isolated"),
    [
        ([], []),
        (["pillar_weights"], []),
        (["other"], []),
        (["d_sat", "other"], ["d_sat"]),
        (["alpha_a", "d_sat"], ["alpha_a", "d_sat"]),
        (
            ["pillar_weights", "alpha_a", "d_sat", "other"],
            ["pillar_weights", "alpha_a", "d_sat"],
        ),
    ],
)
def test_only_two_or_more_factors_are_isolated_and_never_other(
    factors: list[str], isolated: list[str]
) -> None:
    assert factors_to_isolate(factors) == isolated


def decimals(values: dict[str, str]) -> dict[str, Decimal]:
    return {key: Decimal(value) for key, value in values.items()}


@pytest.mark.parametrize("factor", ["pillar_weights", "alpha_a", "d_sat"])
def test_isolated_values_take_only_that_factor_and_stay_valid(factor: str) -> None:
    values = isolated_values(decimals(DEFAULTS), decimals(SPREAD), factor)

    assert values == decimals({**DEFAULTS, **ISOLATED[factor]})
    descriptor = get_descriptor("scoring-model", 1)
    assert descriptor is not None
    assert validate_values(descriptor, values).valid
    ScoringParameters.from_values(values)


def socio_totals(*totals: str) -> list[StoredEntry]:
    return [
        StoredEntry(uuid.uuid4(), i + 1, {}, Decimal(t), {})
        for i, t in enumerate(totals)
    ]


def simulated(before: list[StoredEntry], *totals: str) -> list[SimulatedEntry]:
    return [
        SimulatedEntry(e.socio_id, e.position, {}, Decimal(t))
        for e, t in zip(before, totals, strict=True)
    ]


def test_the_mean_total_change_is_exact() -> None:
    before = socio_totals("10.00", "20.00", "30.00")
    after = simulated(before, "10.01", "20.00", "30.00")

    assert mean_total_change(before, after) == Fraction(1, 300)


def test_the_mean_total_change_needs_the_same_socios() -> None:
    before = socio_totals("10.00", "20.00")
    with pytest.raises(ValueError):
        mean_total_change(before, simulated(before[:1], "10.00"))
    with pytest.raises(ValueError):
        mean_total_change([], [])


def effect(factor: str, mean_abs: str) -> FactorEffect:
    moved = Movement(0, 0, 0, Decimal(mean_abs), 1, 0, 0)
    return FactorEffect(factor, (), Fraction(0), moved)


def test_effects_go_from_the_largest_to_the_smallest_change_of_position() -> None:
    effects = [
        effect("pillar_weights", "1.2"),
        effect("alpha_a", "3.5"),
        effect("d_sat", "2"),
    ]

    assert [e.factor for e in rank_effects(effects)] == [
        "alpha_a",
        "d_sat",
        "pillar_weights",
    ]


def test_ties_go_pillar_weights_then_alpha_a_then_d_sat() -> None:
    effects = [
        effect("d_sat", "2"),
        effect("alpha_a", "2"),
        effect("pillar_weights", "2"),
    ]

    assert [e.factor for e in rank_effects(effects)] == [
        "pillar_weights",
        "alpha_a",
        "d_sat",
    ]


def test_a_tiny_exact_difference_is_not_a_tie() -> None:
    # 1/3 contra 0.3333…: el más chico va después aunque redondeado se vea igual.
    effects = [effect("pillar_weights", "0.3333"), effect("d_sat", str(Decimal(1) / 3))]

    assert [e.factor for e in rank_effects(effects)] == ["d_sat", "pillar_weights"]

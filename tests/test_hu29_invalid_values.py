"""HU-29, escenario 6: validación de los valores hipotéticos.

"Given hypothetical values, When any is missing, is not a number, is outside the limits of its
parameter, is not a parameter of the formula, or the pillar weights do not add up to 1.00,
Then the simulation is blocked with `INVALID_VALUES` and the list of violations, each with the
code and text of HU-27. All violations are returned together and nothing is calculated."
Contrato: `docs/contrato-api-simulacion-reglas.md` §4.1.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Ranking, RankingEntry, RulesVersion, User
from app.scoring.catalog import SCORING_MODEL_V1
from app.scoring.validation import validate_values
from app.services import rules_simulation_service
from app.services.formula_service import violations_out
from tests.conftest import Outbox
from tests.hu25_helpers import DEFAULTS, RUNS, headers_for, make_socio, publish_rules

SIMULATOR = "/admin/rules-simulation"
INVALID_VALUES_MESSAGE = (
    "Hay valores que no se pueden simular. Corregilos y volvé a intentar."
)
SUM_LABEL = "Los pesos de asistencia, participación institucional y antigüedad y edad"


@pytest.fixture
def boca(
    client: TestClient, db: Session, outbox: Outbox, admin: User
) -> dict[str, str]:
    """Admin de Boca con un ranking completado de dos socios."""
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    make_socio(db)
    make_socio(db)
    response = client.post(RUNS, headers=headers)
    assert response.status_code == 201, response.text
    return headers


def simulate(
    client: TestClient, headers: dict[str, str], values: dict[str, Any]
) -> Any:
    return client.post(SIMULATOR, json={"values": values}, headers=headers)


def violations_of(response: Any) -> list[dict[str, Any]]:
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "INVALID_VALUES"
    assert detail["message"] == INVALID_VALUES_MESSAGE
    return list(detail["violations"])


def with_values(**overrides: Any) -> dict[str, Any]:
    return {**DEFAULTS, **overrides}


# --- Aceptación ----------------------------------------------------------------------------


def test_all_violations_are_returned_together_with_the_texts_of_hu27(
    client: TestClient, boca: dict[str, str]
) -> None:
    values = with_values(w_a="0.65", alpha_a="mucho", d_sat="5000", zeta="1")
    del values["gamma"]

    response = simulate(client, boca, values)

    assert violations_of(response) == [
        {
            "code": "PARAMETER_NOT_A_NUMBER",
            "parameter": "alpha_a",
            "message": "El valor de «Peso de la distancia dentro de la asistencia» "
            "tiene que ser un número.",
        },
        {
            "code": "PARAMETER_OUT_OF_LIMITS",
            "parameter": "d_sat",
            "message": "«Distancia de saturación» tiene que estar entre 50 y 3000 km.",
        },
        {
            "code": "PARAMETER_MISSING",
            "parameter": "gamma",
            "message": "Falta el valor de «Curvatura».",
        },
        {
            "code": "SUM_CONSTRAINT_VIOLATED",
            "parameter": None,
            "message": f"{SUM_LABEL} tienen que sumar 1; hoy suman 1,05.",
        },
        {
            "code": "PARAMETER_UNKNOWN",
            "parameter": "zeta",
            "message": "«zeta» no es un parámetro de esta fórmula.",
        },
    ]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("values", "code", "parameter"),
    [
        (
            {k: v for k, v in DEFAULTS.items() if k != "t_ref"},
            "PARAMETER_MISSING",
            "t_ref",
        ),
        (with_values(t_ref=""), "PARAMETER_MISSING", "t_ref"),
        (with_values(t_ref=None), "PARAMETER_MISSING", "t_ref"),
        (with_values(t_ref="diez"), "PARAMETER_NOT_A_NUMBER", "t_ref"),
        (with_values(t_ref=True), "PARAMETER_NOT_A_NUMBER", "t_ref"),
        (with_values(t_ref="NaN"), "PARAMETER_NOT_A_NUMBER", "t_ref"),
        (with_values(t_ref="9.99"), "PARAMETER_OUT_OF_LIMITS", "t_ref"),
        (with_values(t_ref="100.01"), "PARAMETER_OUT_OF_LIMITS", "t_ref"),
        (with_values(b="0.004"), "PARAMETER_UNKNOWN", "b"),
        (with_values(w_t="0.19"), "SUM_CONSTRAINT_VIOLATED", None),
    ],
    ids=[
        "falta",
        "vacio",
        "nulo",
        "texto",
        "booleano",
        "nan",
        "debajo-del-minimo",
        "encima-del-maximo",
        "derivado-no-es-parametro",
        "pesos-no-suman-1",
    ],
)
def test_each_kind_of_violation_blocks_the_simulation(
    client: TestClient,
    boca: dict[str, str],
    values: dict[str, Any],
    code: str,
    parameter: str | None,
) -> None:
    response = simulate(client, boca, values)

    [violation] = violations_of(response)
    assert (violation["code"], violation["parameter"]) == (code, parameter)


def test_the_violations_are_exactly_the_ones_of_hu27(
    client: TestClient, boca: dict[str, str]
) -> None:
    """Misma validación que publicar o ajustar: mismos códigos, textos y orden."""
    values = with_values(w_a="2", w_p="-1", t_carencia="1096", b_max="4,9", extra="x")

    response = simulate(client, boca, values)

    expected = violations_out(validate_values(SCORING_MODEL_V1, values).violations)
    assert violations_of(response) == expected
    # Cuatro fuera de límites, la suma (2 − 1 + 0,2 = 1,2) y el desconocido.
    assert len(expected) == 6


def test_without_values_every_parameter_is_missing(
    client: TestClient, boca: dict[str, str]
) -> None:
    violations = violations_of(simulate(client, boca, {}))

    assert [v["code"] for v in violations] == ["PARAMETER_MISSING"] * 13
    assert [v["parameter"] for v in violations] == [
        p.key for p in SCORING_MODEL_V1.parameters
    ]


def test_invalid_values_change_nothing(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    counts = [
        db.scalar(select(func.count()).select_from(model))
        for model in (RulesVersion, Ranking, RankingEntry)
    ]

    simulate(client, boca, with_values(d_sat="0"))

    db.expire_all()
    assert [
        db.scalar(select(func.count()).select_from(model))
        for model in (RulesVersion, Ranking, RankingEntry)
    ] == counts


@pytest.mark.parametrize("path", ["", "/breakdown", "/export"])
def test_with_invalid_values_no_simulation_runs(
    client: TestClient,
    db: Session,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    # SC-008: 0 simulaciones con pesos que no suman 1,00; ni se leen las entradas.
    def must_not_run(*_: Any, **__: Any) -> None:
        raise AssertionError("Se simuló con valores inválidos.")

    for name in ("stored_entries", "simulate_entries", "PillarSimulator"):
        monkeypatch.setattr(rules_simulation_service, name, must_not_run)
    ranking_id = db.scalar(select(Ranking.id))
    values = with_values(w_a="0.65")

    response = client.post(
        f"{SIMULATOR}{path}",
        json={"ranking_id": ranking_id, "values": values},
        headers=boca,
    )

    assert [v["code"] for v in violations_of(response)] == ["SUM_CONSTRAINT_VIOLATED"]


# --- Aceptación: valores válidos ------------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        DEFAULTS,
        # Decimales, no coma flotante: 0,7 + 0,1 + 0,2 suman exactamente 1.
        with_values(w_a="0.7", w_p="0.1", w_t="0.2"),
        with_values(w_a=0.7, w_p=0.1, w_t=0.2, d_sat=800),
        # Ceros de más y coma decimal, como en HU-27.
        with_values(w_a="0.600", w_p="0,20", w_t="0.2000"),
        # Los límites son inclusivos.
        with_values(d_sat="50", t_carencia="1095", gamma="0.5"),
    ],
    ids=["por-defecto", "suma-exacta", "numeros-json", "ceros-y-coma", "limites"],
)
def test_valid_values_are_simulated(
    client: TestClient, boca: dict[str, str], values: dict[str, Any]
) -> None:
    response = simulate(client, boca, values)

    assert response.status_code == 200, response.text
    assert response.json()["ranking"]["population_size"] == 2

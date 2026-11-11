"""HU-29, escenario 22: cada simulación aislada sigue las reglas de los escenarios 6, 8 y 9.

"Given an isolated simulation, When it is computed, Then it follows every rule of scenarios 6,
8 and 9: same validation, same calculation, same tiebreak, no real data modified. Any shortcut
used to compute it MUST give exactly the same result as a full recomputation (parity test)."
Contrato: `docs/contrato-api-simulacion-reglas.md` §8 (atajo por factor); SC-003.

El mismo cálculo y el mismo desempate frente a un HU-25 real están en
`test_hu29_breakdown.py`; que no modifica datos reales, también. Acá: el atajo por pilares
(`PillarSimulator`) contra el cálculo completo (`simulate_entries`) y la validación.
"""

import random
import uuid
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, User
from app.scoring.attendance_inputs import MATCH_CLASSES
from app.scoring.engine import (
    PILLAR_PARAMETERS,
    ScoringInputs,
    ScoringParameters,
    calculate_score,
    combine_pillars,
    pillar,
    pillar_inputs,
    score_pillars,
)
from app.scoring.rules_simulation import PillarSimulator, StoredEntry, simulate_entries
from app.scoring.snapshot import scoring_inputs_from_snapshot
from app.services import rules_simulation_service
from app.services.rules_simulation_service import stored_entries
from tests.conftest import Outbox
from tests.hu25_helpers import DEFAULTS, headers_for, publish_rules
from tests.hu29_helpers import (
    SIMULATOR,
    SPREAD,
    TO_THE_CAP,
    make_saturation_club,
    run_ranking,
)

BREAKDOWN = f"{SIMULATOR}/breakdown"
# Juegos de valores que tocan cada pilar y la combinación, en un orden que reusa pilares:
# pesos y αA sobre los del ranking, dsat solo, otros parámetros (γ no entero, carencia), tope.
VALUE_SETS = [
    DEFAULTS,
    {**DEFAULTS, "w_a": "0.5", "w_p": "0.3"},
    {**DEFAULTS, "alpha_a": "1"},
    {**DEFAULTS, "alpha_a": "0"},
    {**DEFAULTS, "d_sat": "100"},
    SPREAD,
    {**DEFAULTS, "gamma": "0.73", "alpha_t": "0.35", "t_ref": "31", "e_ref": "77"},
    {**DEFAULTS, "p_inst_max": "37", "b_max": "40", "t_max": "45", "t_carencia": "30"},
    TO_THE_CAP,
    {**SPREAD, "gamma": "1.7", "d_sat": "2999"},
    DEFAULTS,
]


def params(values: dict[str, str]) -> ScoringParameters:
    return ScoringParameters.from_values(values)


def snapshot(rng: random.Random, dni: int) -> dict[str, Any]:
    """Una instantánea al azar (con semilla) que cubre los bordes de cada pilar."""
    matches = {c: rng.choice([0, 0, 3, 10]) for c in MATCH_CLASSES}
    attended = {c: rng.randint(0, n) for c, n in matches.items()}
    born = date(1940, 1, 1) + timedelta(days=rng.randint(0, 25000))
    start = born + timedelta(days=rng.randint(0, 20000))
    return {
        "attendance": {
            "matches_by_class": matches,
            "attended_by_class": attended,
            # Distancias repetidas y distintas, para que el atajo comparta y no comparta.
            "distance_km": rng.choice(
                ["0.00", "5.00", "1200.00", f"{rng.uniform(0, 3000):.2f}"]
            ),
        },
        "institutional": {"points": rng.choice([0, 37, 100, rng.randint(0, 250)])},
        "membership": {
            "seniority_years": rng.randint(0, 70),
            "age_years": rng.randint(0, 95),
            "days_since_alta": rng.choice([0, 30, 179, 180, rng.randint(0, 30000)]),
            "days_between_previous_baja_and_alta": rng.choice([None, 0, 29, 30, 400]),
            "seniority_start": start.isoformat(),
            "birth_date": born.isoformat(),
        },
        # Documentos repetidos: el desempate tiene que llegar hasta el final igual.
        "tiebreak": {"dni": str(10_000_000 + dni % 700)},
    }


def random_ranking(size: int) -> list[StoredEntry]:
    rng = random.Random(22)
    return [
        StoredEntry(uuid.uuid4(), i + 1, {}, Decimal(0), snapshot(rng, i))
        for i in range(size)
    ]


# --- Paridad del atajo ---------------------------------------------------------------------


def test_the_pillar_shortcut_gives_exactly_the_full_recalculation() -> None:
    entries = random_ranking(1500)
    simulator = PillarSimulator(entries)

    for values in VALUE_SETS:
        assert simulator.run(params(values)) == simulate_entries(
            entries, params(values)
        ), values


def test_the_shortcut_gives_the_full_recalculation_over_a_real_ranking(
    client: TestClient, outbox: Outbox, admin: User, db: Session
) -> None:
    publish_rules(client, headers_for(client, outbox, admin))
    make_saturation_club(db)
    entries = stored_entries(db, run_ranking(db, admin).id)
    simulator = PillarSimulator(entries)

    for values in VALUE_SETS:
        assert simulator.run(params(values)) == simulate_entries(
            entries, params(values)
        ), values


def test_the_score_is_by_definition_the_combination_of_its_pillars() -> None:
    entries = random_ranking(300)
    for values in VALUE_SETS:
        for entry in entries:
            inputs = scoring_inputs_from_snapshot(entry.snapshot)
            expected = calculate_score(inputs, params(values))
            got = combine_pillars(score_pillars(inputs, params(values)), params(values))
            assert got == expected


OTHER_INPUTS = ScoringInputs(
    matches_by_class={"A": 9, "B": 7, "C": 5},
    attended_by_class={"A": 9, "B": 7, "C": 4},
    distance_km=Decimal("2500.25"),
    institutional_points=Decimal(222),
    seniority_years=Decimal(66),
    age_years=Decimal(91),
    days_since_alta=29999,
    days_since_previous_baja=1,
)
SOME_INPUTS = ScoringInputs(
    matches_by_class={"A": 3, "B": 2, "C": 1},
    attended_by_class={"A": 2, "B": 0, "C": 1},
    distance_km=Decimal("15.50"),
    institutional_points=Decimal(40),
    seniority_years=Decimal(12),
    age_years=Decimal(45),
    days_since_alta=100,
    days_since_previous_baja=None,
)
# Qué insumos lee cada pilar; el resto no puede cambiarlo.
READS = {
    "frequency": ("matches_by_class", "attended_by_class"),
    "distance": ("distance_km", "attended_by_class"),
    "institutional": ("institutional_points",),
    "seniority_age": ("seniority_years", "age_years"),
    "new_member_bonus": ("days_since_alta", "days_since_previous_baja"),
}


@pytest.mark.parametrize("name", list(PILLAR_PARAMETERS))
def test_a_pillar_depends_only_on_the_inputs_that_share_it(name: str) -> None:
    # Cambiar todo lo que el pilar no lee no cambia ni su valor ni sus insumos compartidos.
    kept = {field: getattr(SOME_INPUTS, field) for field in READS[name]}
    mixed = replace(OTHER_INPUTS, **kept)

    assert pillar_inputs(name, mixed) == pillar_inputs(name, SOME_INPUTS)
    for values in VALUE_SETS:
        assert pillar(name, mixed, params(values)) == pillar(
            name, SOME_INPUTS, params(values)
        )


@pytest.mark.parametrize("name", list(PILLAR_PARAMETERS))
def test_a_pillar_depends_only_on_its_parameters(name: str) -> None:
    # Cambiar los parámetros que el pilar no usa no lo cambia.
    base = params(DEFAULTS)
    for values in VALUE_SETS:
        other = params(values)
        same = replace(
            other, **{key: getattr(base, key) for key in PILLAR_PARAMETERS[name]}
        )
        assert pillar(name, SOME_INPUTS, same) == pillar(name, SOME_INPUTS, base)


def test_an_unknown_pillar_is_an_error() -> None:
    with pytest.raises(ValueError):
        pillar("otro", SOME_INPUTS, params(DEFAULTS))
    with pytest.raises(ValueError):
        pillar_inputs("otro", SOME_INPUTS)


# --- Misma validación ----------------------------------------------------------------------


def test_isolated_values_that_do_not_validate_make_the_breakdown_unavailable(
    client: TestClient,
    outbox: Outbox,
    admin: User,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    make_saturation_club(db)
    ranking: Ranking = run_ranking(db, admin)
    # Si un juego aislado no pasara la validación de HU-27, no se simula con él.
    monkeypatch.setattr(
        rules_simulation_service,
        "isolated_values",
        lambda before, *_: {**before, "w_a": Decimal("0.9")},
    )

    response = client.post(
        BREAKDOWN, json={"ranking_id": ranking.id, "values": SPREAD}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["code"] == "BREAKDOWN_UNAVAILABLE"

"""HU-29, escenario 8: recálculo desde la instantánea de cada entrada.

"Given valid hypothetical values, When the simulation runs, Then every Socio of the latest
completed ranking is recomputed from the stored inputs snapshot of its entry, with the
calculation of the formula (the same one HU-25 uses) and the tiebreak of the scoring model
(rule 5), obtaining components, total and position; no real data is modified and no source
data is re-read. The population is exactly the Socios of that ranking."
Contrato: `docs/contrato-api-simulacion-reglas.md` §5.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models import AsistenciaDB, Ranking, RankingEntry, RulesVersion, Socio, User
from app.scoring.components import COMPONENT_KEYS
from app.scoring.engine import ScoringParameters
from app.scoring.rules_simulation import (
    Movement,
    SimulatedEntry,
    StoredEntry,
    changed_keys,
    factor_of,
    factors_changed,
    movement,
    simulate_entries,
)
from app.services.rules_simulation_service import stored_entries
from tests.conftest import Outbox
from tests.hu25_helpers import (
    DEFAULTS,
    adjust_rules,
    entries_of,
    headers_for,
    make_socio,
    publish_rules,
)
from tests.hu29_helpers import (
    CHANGED,
    SIMULATOR,
    VariedClub,
    make_varied_club,
    run_ranking,
)


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


@pytest.fixture
def club(db: Session, boca: dict[str, str]) -> VariedClub:
    return make_varied_club(db)


@pytest.fixture
def ranking(db: Session, admin: User, club: VariedClub) -> Ranking:
    return run_ranking(db, admin)


def simulate(
    client: TestClient, headers: dict[str, str], values: dict[str, Any]
) -> Any:
    response = client.post(SIMULATOR, json={"values": values}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def scored(entry: RankingEntry | SimulatedEntry) -> tuple[Any, ...]:
    components = (
        entry.components
        if isinstance(entry, SimulatedEntry)
        else {key: getattr(entry, key) for key in COMPONENT_KEYS}
    )
    return (entry.position, entry.total, *(components[key] for key in COMPONENT_KEYS))


# --- Aceptación: mismo cálculo y mismo desempate que HU-25 ---------------------------------


def test_the_simulation_gives_what_hu25_would_calculate_with_those_rules(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
) -> None:
    simulated = simulate_entries(
        stored_entries(db, ranking.id), ScoringParameters.from_values(CHANGED)
    )
    # La verdad: un cálculo real de HU-25 con esas reglas, en el mismo momento y con los
    # mismos datos.
    adjust_rules(client, boca, 1, **CHANGED)
    official = run_ranking(db, admin)

    expected = {e.socio_id: scored(e) for e in entries_of(db, official)}
    assert {e.socio_id: scored(e) for e in simulated} == expected
    # El cambio de reglas mueve el ranking: si no, el test no probaría el reordenamiento.
    before = {e.socio_id: e.position for e in entries_of(db, ranking)}
    assert any(before[e.socio_id] != e.position for e in simulated)


def test_the_result_counts_the_movement_against_the_ranking(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    ranking: Ranking,
) -> None:
    body = simulate(client, boca, CHANGED)
    adjust_rules(client, boca, 1, **CHANGED)
    official = {e.socio_id: e.position for e in entries_of(db, run_ranking(db, admin))}

    changes = [e.position - official[e.socio_id] for e in entries_of(db, ranking)]
    assert body["status"] == "changed"
    assert body["message"] is None
    assert body["movement"] == {
        "up": sum(1 for c in changes if c > 0),
        "down": sum(1 for c in changes if c < 0),
        "unchanged": sum(1 for c in changes if c == 0),
    }
    assert sum(body["movement"].values()) == ranking.population_size == 7


def test_the_result_lists_the_changed_parameters_and_their_factors(
    client: TestClient, boca: dict[str, str], ranking: Ranking
) -> None:
    body = simulate(client, boca, CHANGED)

    assert body["changed_parameters"] == [
        {
            "key": "w_a",
            "symbol": "wA",
            "name": "Peso de la asistencia",
            "factor": "pillar_weights",
            "before": "0.6",
            "after": "0.5",
        },
        {
            "key": "w_p",
            "symbol": "wP",
            "name": "Peso de la participación institucional",
            "factor": "pillar_weights",
            "before": "0.2",
            "after": "0.3",
        },
        {
            "key": "alpha_a",
            "symbol": "αA",
            "name": "Peso de la distancia dentro de la asistencia",
            "factor": "alpha_a",
            "before": "0.2",
            "after": "0.4",
        },
        {
            "key": "d_sat",
            "symbol": "dsat",
            "name": "Distancia de saturación",
            "factor": "d_sat",
            "before": "1200",
            "after": "600",
        },
        {
            "key": "b_max",
            "symbol": "Bmax",
            "name": "Bono de bienvenida",
            "factor": "other",
            "before": "15",
            "after": "20",
        },
    ]
    assert body["factors_changed"] == ["pillar_weights", "alpha_a", "d_sat", "other"]


def test_ties_are_broken_with_the_snapshot_down_to_the_document(
    db: Session, club: VariedClub, ranking: Ranking
) -> None:
    simulated = simulate_entries(
        stored_entries(db, ranking.id), ScoringParameters.from_values(CHANGED)
    )

    by_socio = {e.socio_id: e for e in simulated}
    low, high = by_socio[club.twin_low_dni.id], by_socio[club.twin_high_dni.id]
    assert low.total == high.total
    # "4000000" va antes que "30000001": se compara como número.
    assert low.position + 1 == high.position
    assert sorted(e.position for e in simulated) == list(range(1, 8))


# --- Aceptación: solo la instantánea; nada se relee ni se modifica -------------------------


def test_source_data_is_not_re_read(
    client: TestClient,
    db: Session,
    club: VariedClub,
    boca: dict[str, str],
    ranking: Ranking,
) -> None:
    first = simulate(client, boca, CHANGED)
    # Después del ranking cambian los datos del club: distancias, documentos, asistencias,
    # fechas, y llega un socio nuevo.
    db.execute(update(Socio).values(distancia_km=Decimal("1.00")))
    db.execute(
        update(Socio)
        .where(Socio.id == club.twin_low_dni.id)
        .values(dni="99999999", fecha_alta=date(2026, 10, 1))
    )
    db.execute(delete(AsistenciaDB))
    db.commit()
    make_socio(db)

    again = simulate(client, boca, CHANGED)
    unchanged = simulate(client, boca, DEFAULTS)

    assert again == first
    assert unchanged["movement"] == {"up": 0, "down": 0, "unchanged": 7}


def test_the_population_is_exactly_the_socios_of_the_ranking(
    db: Session, club: VariedClub, ranking: Ranking
) -> None:
    make_socio(db)

    stored = stored_entries(db, ranking.id)
    simulated = simulate_entries(stored, ScoringParameters.from_values(CHANGED))

    assert [e.socio_id for e in simulated] == [e.socio_id for e in stored]
    assert {e.socio_id for e in simulated} == {s.id for s in club.socios}


def test_simulating_modifies_no_real_data(
    client: TestClient, db: Session, boca: dict[str, str], ranking: Ranking
) -> None:
    stored_before = stored_entries(db, ranking.id)
    counts_before = [
        db.scalar(select(func.count()).select_from(model))
        for model in (RulesVersion, Ranking, RankingEntry)
    ]

    simulate(client, boca, CHANGED)
    simulate(client, boca, CHANGED)

    db.expire_all()
    assert stored_entries(db, ranking.id) == stored_before
    assert [
        db.scalar(select(func.count()).select_from(model))
        for model in (RulesVersion, Ranking, RankingEntry)
    ] == counts_before


# --- Unitarias -----------------------------------------------------------------------------


def entry(position: int) -> StoredEntry:
    return StoredEntry(uuid.uuid4(), position, {}, Decimal(0), {})


def moved_to(stored: StoredEntry, position: int) -> SimulatedEntry:
    return SimulatedEntry(stored.socio_id, position, {}, Decimal(0))


def test_movement_counts_up_down_and_unchanged() -> None:
    before = [entry(1), entry(2), entry(3), entry(4)]
    after = [moved_to(before[0], 3), moved_to(before[1], 1), moved_to(before[2], 2)]
    after.append(moved_to(before[3], 4))

    assert movement(before, after) == Movement(up=2, down=1, unchanged=1)


@pytest.mark.parametrize(
    ("key", "factor"),
    [
        ("w_a", "pillar_weights"),
        ("w_p", "pillar_weights"),
        ("w_t", "pillar_weights"),
        ("alpha_a", "alpha_a"),
        ("d_sat", "d_sat"),
        ("p_inst_max", "other"),
        ("alpha_t", "other"),
        ("t_ref", "other"),
        ("e_ref", "other"),
        ("gamma", "other"),
        ("b_max", "other"),
        ("t_max", "other"),
        ("t_carencia", "other"),
    ],
)
def test_each_parameter_belongs_to_its_factor(key: str, factor: str) -> None:
    assert factor_of(key) == factor


def test_values_are_compared_as_decimals() -> None:
    before = {"w_a": Decimal("0.6"), "d_sat": Decimal(1200), "gamma": Decimal(1)}
    after = {
        "w_a": Decimal("0.60"),
        "d_sat": Decimal("1200.0"),
        "gamma": Decimal("0.9"),
    }

    assert changed_keys(before, after) == ["gamma"]


def test_factors_keep_their_fixed_order() -> None:
    assert factors_changed(["b_max", "d_sat", "w_t", "w_a"]) == [
        "pillar_weights",
        "d_sat",
        "other",
    ]
    assert factors_changed([]) == []

"""HU-25, Ciclo 3c: componentes, tope, bono y snapshot de entradas (esc. 8, FR-002).

Cada entrada guarda los seis componentes, el total, la posición y la instantánea de entradas
con la que se calculó. Con esa instantánea y las mismas reglas el cálculo es reproducible.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Ranking, RankingEntry, Socio, User, utcnow
from app.scoring.components import COMPONENT_KEYS
from app.scoring.engine import ScoringParameters, calculate_score
from app.scoring.snapshot import scoring_inputs_from_snapshot
from app.services import ranking_run_service
from tests.conftest import BOCA_ID, Outbox
from tests.hu25_helpers import (
    RUNS,
    entries_of,
    headers_for,
    load_attendance,
    make_activity,
    make_event,
    make_socio,
    publish_rules,
)

NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
PARAMS = ScoringParameters.defaults()


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


def run_at(db: Session, admin: User, now: datetime = NOW) -> Ranking:
    return ranking_run_service.start_run(db, admin, BOCA_ID, now=now)


def entry_of(db: Session, ranking: Ranking, socio: Socio) -> RankingEntry:
    return db.scalars(
        select(RankingEntry).where(
            RankingEntry.ranking_id == ranking.id, RankingEntry.socio_id == socio.id
        )
    ).one()


def components_of(entry: RankingEntry) -> dict[str, Decimal]:
    return {key: getattr(entry, key) for key in COMPONENT_KEYS}


# --- Aceptación: "Cada entrada guarda sus componentes y su instantánea" --------------------


def test_entry_persists_all_components_and_inputs_snapshot(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    now = utcnow()
    socio = make_socio(db)
    match = make_event(db, id_externo="EVT-PARTIDO", when=now - timedelta(days=2))
    assembly = make_event(
        db,
        id_externo="EVT-ASAMBLEA",
        when=now - timedelta(days=9),
        tipo="Institucional",
        clase=None,
        puntos=40,
    )
    for held in (match, assembly):
        load_attendance(db, held, [socio])

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 201
    assert response.json()["status"] == "completed"
    ranking = db.get_one(Ranking, response.json()["id"])
    entry = entry_of(db, ranking, socio)
    assert entry.position == 1
    assert set(entry.inputs) == {"attendance", "institutional", "membership"}
    # Asistió al único partido (48,00) y a una asamblea de 40 puntos (0,20 · 40).
    assert entry.attendance_frequency == Decimal("48.00")
    assert entry.institutional == Decimal("8.00")
    assert entry.cap_adjustment == Decimal("0.00")
    # La instantánea alcanza para volver a obtener exactamente los mismos componentes.
    expected = calculate_score(scoring_inputs_from_snapshot(entry.inputs), PARAMS)
    assert components_of(entry) == expected.components
    assert entry.total == expected.total


# --- Unitarias: total y posiciones ---------------------------------------------------------


def test_total_equals_sum_of_components(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    veteran = make_socio(db, fecha_alta=date(1990, 1, 1))
    newcomer = make_socio(db, fecha_alta=date(2026, 10, 1))
    active = make_socio(db)
    held = make_event(db, id_externo="EVT-1", when=NOW - timedelta(days=3))
    load_attendance(db, held, [active])

    ranking = run_at(db, admin)

    for socio in (veteran, newcomer, active):
        entry = entry_of(db, ranking, socio)
        assert entry.total == sum(components_of(entry).values(), Decimal("0.00"))


def test_a_higher_total_gets_the_better_position(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    passive = make_socio(db, dni="10000001")
    active = make_socio(db, dni="90000009")
    held = make_event(db, id_externo="EVT-1", when=NOW - timedelta(days=3))
    load_attendance(db, held, [active])

    ranking = run_at(db, admin)

    assert [entry.socio_id for entry in entries_of(db, ranking)] == [
        active.id,
        passive.id,
    ]


# --- Unitarias: bono de nuevo socio --------------------------------------------------------


def test_new_member_bonus_from_alta_date(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    newcomer = make_socio(db, fecha_alta=date(2026, 10, 19))  # t = 10 días
    veteran = make_socio(db, fecha_alta=date(2025, 1, 1))  # t ≥ 180: sin bono
    back_too_soon = make_socio(
        db, fecha_alta=date(2026, 10, 19), fecha_baja_previa=date(2026, 7, 11)
    )  # 100 días entre la baja y el alta: dentro de la carencia
    back_after_a_year = make_socio(
        db, fecha_alta=date(2026, 10, 19), fecha_baja_previa=date(2025, 9, 14)
    )  # 400 días entre la baja y el alta

    ranking = run_at(db, admin)

    # 15 · (1 − 10/180) = 14,17
    assert entry_of(db, ranking, newcomer).new_member_bonus == Decimal("14.17")
    assert entry_of(db, ranking, veteran).new_member_bonus == Decimal("0.00")
    assert entry_of(db, ranking, back_too_soon).new_member_bonus == Decimal("0.00")
    assert entry_of(db, ranking, back_after_a_year).new_member_bonus == Decimal("14.17")


def test_the_score_uses_the_parameters_of_the_published_rules(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca, b_max="10.0")
    newcomer = make_socio(db, fecha_alta=date(2026, 10, 19))

    ranking = run_at(db, admin)

    # 10 · (1 − 10/180) = 9,44
    assert entry_of(db, ranking, newcomer).new_member_bonus == Decimal("9.44")


# --- Unitarias: tope de 100 ----------------------------------------------------------------


def test_cap_adjustment_persisted_when_over_100(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(
        db,
        fecha_nacimiento=date(1940, 1, 1),
        fecha_alta=date(2026, 10, 29),
        distancia_km=Decimal("5000.00"),
    )
    played = make_event(db, id_externo="EVT-1", when=NOW - timedelta(hours=1))
    load_attendance(db, played, [socio])
    make_activity(
        db,
        socio,
        tipo="deporte_federado",
        desde=date(2025, 11, 1),
        hasta=date(2026, 10, 29),
    )

    ranking = run_at(db, admin)

    entry = entry_of(db, ranking, socio)
    assert components_of(entry) == {
        "attendance_frequency": Decimal("48.00"),
        "attendance_distance": Decimal("12.00"),
        "institutional": Decimal("20.00"),
        "seniority_age": Decimal("8.75"),
        "new_member_bonus": Decimal("15.00"),
        "cap_adjustment": Decimal("-3.75"),
    }
    assert entry.total == Decimal("100.00")


# --- Unitarias: antigüedad y snapshot de pertenencia ---------------------------------------


def test_a_previous_baja_restarts_the_seniority_in_the_snapshot(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    continuous = make_socio(db, fecha_alta=date(2016, 10, 29))
    returned = make_socio(
        db, fecha_alta=date(2022, 5, 10), fecha_baja_previa=date(2021, 1, 1)
    )
    baja_after_alta = make_socio(
        db, fecha_alta=date(2016, 10, 29), fecha_baja_previa=date(2020, 1, 1)
    )

    ranking = run_at(db, admin)

    continuous_snapshot = entry_of(db, ranking, continuous).inputs["membership"]
    returned_snapshot = entry_of(db, ranking, returned).inputs["membership"]
    incoherent_snapshot = entry_of(db, ranking, baja_after_alta).inputs["membership"]
    assert continuous_snapshot["seniority_years"] == 10
    assert returned_snapshot["seniority_years"] == 4
    assert returned_snapshot["days_between_previous_baja_and_alta"] == 494
    assert incoherent_snapshot["seniority_start"] == "2020-01-01"
    assert incoherent_snapshot["seniority_years"] == 6


def test_the_membership_snapshot_has_the_documented_shape(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)  # nacido el 1/1/1980, alta el 1/3/2015

    ranking = run_at(db, admin)

    assert entry_of(db, ranking, socio).inputs["membership"] == {
        "birth_date": "1980-01-01",
        "seniority_start": "2015-03-01",
        "seniority_years": 11,
        "age_years": 46,
        "days_since_alta": (date(2026, 10, 29) - date(2015, 3, 1)).days,
        "days_between_previous_baja_and_alta": None,
    }


# --- Reproducibilidad ----------------------------------------------------------------------


def test_same_snapshot_and_rules_give_same_ranking(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    active = make_socio(db, fecha_alta=date(2026, 9, 1))
    other = make_socio(db, fecha_baja_previa=date(2014, 1, 1))
    held = make_event(db, id_externo="EVT-1", when=NOW - timedelta(days=3))
    load_attendance(db, held, [active])

    first = run_at(db, admin)
    second = run_at(db, admin)

    assert first.id != second.id
    for socio in (active, other):
        a, b = entry_of(db, first, socio), entry_of(db, second, socio)
        assert (components_of(a), a.total, a.position, a.inputs) == (
            components_of(b),
            b.total,
            b.position,
            b.inputs,
        )
        recomputed = calculate_score(scoring_inputs_from_snapshot(a.inputs), PARAMS)
        assert components_of(a) == recomputed.components

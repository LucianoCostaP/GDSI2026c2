"""HU-25, Ciclo 3a: ventana de asistencia y datos de entrada (esc. 8, FR-008).

Cada entrada del ranking guarda en `inputs["attendance"]` los partidos que cuentan para ese
socio (por clase), a cuántos fue y su distancia. El motor de scoring (Ciclo 0) los convierte
en puntaje; acá se verifica qué datos entran.
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.date_utils import BUENOS_AIRES_TZ, a_hora_buenos_aires
from app.models import (
    EstadoCargaParticipacion,
    Ranking,
    RankingEntry,
    Socio,
    User,
    utcnow,
)
from app.services import ranking_run_service
from tests.conftest import BOCA_ID, RIVER_ID, Outbox
from tests.hu25_helpers import (
    RUNS,
    entries_of,
    headers_for,
    load_attendance,
    make_event,
    make_socio,
    publish_rules,
)

NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


def ba(year: int, month: int, day: int, hour: int = 20, minute: int = 0) -> datetime:
    """Momento en hora de Buenos Aires."""
    return datetime(year, month, day, hour, minute, tzinfo=BUENOS_AIRES_TZ)


def run_at(db: Session, admin: User, now: datetime = NOW) -> Ranking:
    return ranking_run_service.start_run(db, admin, BOCA_ID, now=now)


def attendance_of(db: Session, ranking: Ranking, socio: Socio) -> dict[str, Any]:
    entry = db.scalars(
        select(RankingEntry).where(
            RankingEntry.ranking_id == ranking.id, RankingEntry.socio_id == socio.id
        )
    ).one()
    return entry.inputs["attendance"]


def by_class(a: int = 0, b: int = 0, c: int = 0) -> dict[str, int]:
    return {"A": a, "B": b, "C": c}


# --- Aceptación: "Ventana de asistencia" ---------------------------------------------------


def test_only_previous_year_and_current_year_to_date_count(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    now = utcnow()
    this_year = a_hora_buenos_aires(now).year
    socio = make_socio(db, fecha_alta=date(2000, 1, 1))
    two_years_ago = make_event(
        db, id_externo="EVT-2Y", when=ba(this_year - 2, 6, 15), clase="C"
    )
    previous_year = make_event(
        db, id_externo="EVT-1Y", when=ba(this_year - 1, 6, 15), clase="A"
    )
    this_year_to_date = make_event(
        db, id_externo="EVT-NOW", when=now - timedelta(hours=1), clase="B"
    )
    for event in (two_years_ago, previous_year, this_year_to_date):
        load_attendance(db, event, [socio])

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 201
    ranking = db.get_one(Ranking, response.json()["id"])
    attendance = attendance_of(db, ranking, socio)
    assert attendance["matches_by_class"] == by_class(a=1, b=1)
    assert attendance["attended_by_class"] == by_class(a=1, b=1)
    assert attendance["window_start"] == f"{this_year - 1}-01-01"


# --- Aceptación: "Partido sin asistencia cargada no es ausencia" ---------------------------


def test_a_played_match_without_loaded_attendance_does_not_add_to_the_denominator(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    now = utcnow()
    socio = make_socio(db)
    loaded = make_event(
        db, id_externo="EVT-LOADED", when=now - timedelta(days=10), clase="B"
    )
    make_event(db, id_externo="EVT-UNLOADED", when=now - timedelta(days=5), clase="A")
    load_attendance(db, loaded, [socio])

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 201
    ranking = db.get_one(Ranking, response.json()["id"])
    attendance = attendance_of(db, ranking, socio)
    assert attendance["matches_by_class"] == by_class(b=1)
    assert attendance["attended_by_class"] == by_class(b=1)


def test_a_loaded_match_the_socio_missed_does_count_as_an_absence(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    other = make_socio(db)
    event = make_event(
        db, id_externo="EVT-1", when=utcnow() - timedelta(days=3), clase="B"
    )
    load_attendance(db, event, [other])

    response = client.post(RUNS, headers=boca)

    ranking = db.get_one(Ranking, response.json()["id"])
    missed = attendance_of(db, ranking, socio)
    assert missed["matches_by_class"] == by_class(b=1)
    assert missed["attended_by_class"] == by_class()
    assert attendance_of(db, ranking, other)["attended_by_class"] == by_class(b=1)


# --- Unitarias: ventana con reloj inyectable -----------------------------------------------


@pytest.mark.parametrize(
    ("now", "calculation_date", "window_start"),
    [
        # 01:30 UTC del 1/1/2027 son las 22:30 del 31/12/2026 en Buenos Aires.
        (datetime(2027, 1, 1, 1, 30, tzinfo=UTC), date(2026, 12, 31), "2025-01-01"),
        (datetime(2027, 1, 1, 12, 0, tzinfo=UTC), date(2027, 1, 1), "2026-01-01"),
    ],
)
def test_window_start_is_jan_1_of_previous_year(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    now: datetime,
    calculation_date: date,
    window_start: str,
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)

    ranking = run_at(db, admin, now)

    assert ranking.calculation_date == calculation_date
    assert attendance_of(db, ranking, socio)["window_start"] == window_start


def test_window_lower_bound_is_midnight_in_buenos_aires(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    # 23:30 del 31/12/2024 en Buenos Aires ya es 2025 en UTC: igual queda afuera.
    outside = make_event(
        db, id_externo="EVT-OUT", when=ba(2024, 12, 31, 23, 30), clase="C"
    )
    inside = make_event(db, id_externo="EVT-IN", when=ba(2025, 1, 1, 0, 30), clase="A")
    for event in (outside, inside):
        load_attendance(db, event, [socio])

    ranking = run_at(db, admin)

    assert attendance_of(db, ranking, socio)["matches_by_class"] == by_class(a=1)


def test_matches_not_yet_played_are_ignored(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    played = make_event(db, id_externo="EVT-PLAYED", when=NOW - timedelta(hours=1))
    upcoming = make_event(db, id_externo="EVT-NEXT", when=NOW + timedelta(hours=1))
    for event in (played, upcoming):
        load_attendance(db, event, [socio])

    ranking = run_at(db, admin)

    assert attendance_of(db, ranking, socio)["matches_by_class"] == by_class(b=1)


# --- Unitarias: denominador desde max(alta, inicio de ventana) -----------------------------


def test_denominator_starts_at_max_alta_window_start(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db, fecha_alta=date(2026, 3, 10))
    events = [
        make_event(db, id_externo="EVT-BEFORE", when=ba(2026, 3, 9), clase="A"),
        make_event(db, id_externo="EVT-ALTA-DAY", when=ba(2026, 3, 10, 10), clase="B"),
        make_event(db, id_externo="EVT-OLD", when=ba(2025, 6, 1), clase="C"),
    ]
    for event in events:
        load_attendance(db, event, [socio])

    ranking = run_at(db, admin)

    attendance = attendance_of(db, ranking, socio)
    assert attendance["effective_start"] == "2026-03-10"
    assert attendance["matches_by_class"] == by_class(b=1)
    assert attendance["attended_by_class"] == by_class(b=1)


# --- Unitarias: qué eventos cuentan --------------------------------------------------------


def test_unloaded_events_ignored(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    make_event(db, id_externo="EVT-NO-LOAD", when=NOW - timedelta(days=9))
    pending = make_event(db, id_externo="EVT-PENDING", when=NOW - timedelta(days=8))
    replaced = make_event(db, id_externo="EVT-REPLACED", when=NOW - timedelta(days=7))
    loaded = make_event(db, id_externo="EVT-LOADED", when=NOW - timedelta(days=6))
    load_attendance(
        db, pending, [socio], estado=EstadoCargaParticipacion.PENDING_APPROVAL
    )
    load_attendance(db, replaced, [socio], estado=EstadoCargaParticipacion.REPLACED)
    load_attendance(db, loaded, [socio])

    ranking = run_at(db, admin)

    attendance = attendance_of(db, ranking, socio)
    assert attendance["matches_by_class"] == by_class(b=1)
    assert attendance["attended_by_class"] == by_class(b=1)


def test_only_partido_feeds_attendance(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    assembly = make_event(
        db,
        id_externo="EVT-ASAMBLEA",
        when=NOW - timedelta(days=4),
        tipo="Institucional",
        clase=None,
        puntos=40,
    )
    match = make_event(db, id_externo="EVT-PARTIDO", when=NOW - timedelta(days=3))
    for event in (assembly, match):
        load_attendance(db, event, [socio])

    ranking = run_at(db, admin)

    attendance = attendance_of(db, ranking, socio)
    assert attendance["matches_by_class"] == by_class(b=1)
    assert attendance["attended_by_class"] == by_class(b=1)


def test_partido_without_class_is_ignored(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    unclassified = make_event(
        db, id_externo="EVT-NO-CLASS", when=NOW - timedelta(days=2), clase=None
    )
    load_attendance(db, unclassified, [socio])

    ranking = run_at(db, admin)

    assert attendance_of(db, ranking, socio)["matches_by_class"] == by_class()


def test_events_of_other_clubs_are_ignored(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    river_socio = make_socio(db, club_id=RIVER_ID)
    river_event = make_event(
        db, id_externo="EVT-RIVER", when=NOW - timedelta(days=2), club_id=RIVER_ID
    )
    load_attendance(db, river_event, [river_socio])

    ranking = run_at(db, admin)

    attendance = attendance_of(db, ranking, socio)
    assert attendance["matches_by_class"] == by_class()
    assert attendance["attended_by_class"] == by_class()


def test_attendance_is_read_only_from_the_own_club(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    # Mismo DNI y mismo id_externo de evento en otro club: no es asistencia de este socio.
    river_socio = make_socio(db, club_id=RIVER_ID, dni=socio.dni)
    boca_event = make_event(db, id_externo="EVT-SHARED", when=NOW - timedelta(days=2))
    river_event = make_event(
        db, id_externo="EVT-SHARED", when=NOW - timedelta(days=2), club_id=RIVER_ID
    )
    load_attendance(db, boca_event, [])
    load_attendance(db, river_event, [river_socio])

    ranking = run_at(db, admin)

    attendance = attendance_of(db, ranking, socio)
    assert attendance["matches_by_class"] == by_class(b=1)
    assert attendance["attended_by_class"] == by_class()


# --- Unitarias: datos del socio ------------------------------------------------------------


def test_distance_taken_from_socio(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    near = make_socio(db, distancia_km=Decimal("87.50"))
    far = make_socio(db, distancia_km=Decimal("1180.00"))

    ranking = run_at(db, admin)

    assert attendance_of(db, ranking, near)["distance_km"] == "87.50"
    assert attendance_of(db, ranking, far)["distance_km"] == "1180.00"


def test_every_entry_keeps_its_own_attendance_inputs(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    went = make_socio(db)
    stayed_home = make_socio(db)
    event = make_event(db, id_externo="EVT-1", when=NOW - timedelta(days=1), clase="A")
    load_attendance(db, event, [went])

    ranking = run_at(db, admin)

    assert len(entries_of(db, ranking)) == 2
    assert attendance_of(db, ranking, went)["attended_by_class"] == by_class(a=1)
    assert attendance_of(db, ranking, stayed_home)["attended_by_class"] == by_class()
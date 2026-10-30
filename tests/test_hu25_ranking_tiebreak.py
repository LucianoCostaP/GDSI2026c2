"""HU-25, Ciclo 4: desempates y posiciones únicas (esc. 6, FR-007, SC-002)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, User
from app.services import ranking_run_service
from tests.conftest import BOCA_ID, Outbox
from tests.hu25_helpers import (
    RUNS,
    entries_of,
    headers_for,
    make_socio,
    publish_rules,
)

NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


def run_at(db: Session, admin: User, now: datetime = NOW) -> Ranking:
    return ranking_run_service.start_run(db, admin, BOCA_ID, now=now)


def socios_in_order(db: Session, ranking: Ranking) -> list:
    return [entry.socio_id for entry in entries_of(db, ranking)]


# --- Aceptación: "Empate de puntaje" -------------------------------------------------------


def test_socios_with_the_same_total_are_ordered_by_the_tiebreak_and_positions_are_unique(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    # Todos superan los valores de referencia de antigüedad y edad: mismo total (20,00).
    oldest_member = make_socio(
        db,
        fecha_alta=date(1950, 1, 1),
        fecha_nacimiento=date(1950, 1, 1),
        dni="30000000",
    )
    older_person = make_socio(
        db,
        fecha_alta=date(1960, 1, 1),
        fecha_nacimiento=date(1930, 1, 1),
        dni="40000000",
    )
    lower_dni = make_socio(
        db,
        fecha_alta=date(1960, 1, 1),
        fecha_nacimiento=date(1940, 1, 1),
        dni="10000000",
    )
    higher_dni = make_socio(
        db,
        fecha_alta=date(1960, 1, 1),
        fecha_nacimiento=date(1940, 1, 1),
        dni="20000000",
    )

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 201
    ranking = db.get_one(Ranking, response.json()["id"])
    entries = entries_of(db, ranking)
    assert {entry.total for entry in entries} == {Decimal("20.00")}
    assert [entry.position for entry in entries] == [1, 2, 3, 4]
    assert [entry.socio_id for entry in entries] == [
        oldest_member.id,  # mayor antigüedad
        older_person.id,  # misma antigüedad, mayor edad
        lower_dni.id,  # misma antigüedad y edad, menor documento
        higher_dni.id,
    ]


# --- Unitarias: las fechas exactas deciden -------------------------------------------------


def test_seniority_tiebreak_uses_the_exact_start_date_not_completed_years(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    # Los dos tienen 16 años de antigüedad cumplidos: mismo total.
    later = make_socio(db, fecha_alta=date(2010, 3, 15), dni="10000001")
    earlier = make_socio(db, fecha_alta=date(2010, 1, 2), dni="90000009")

    ranking = run_at(db, admin)

    entries = entries_of(db, ranking)
    assert entries[0].total == entries[1].total
    assert socios_in_order(db, ranking) == [earlier.id, later.id]


def test_age_tiebreak_uses_the_exact_birth_date_not_completed_years(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    # Los dos tienen 46 años cumplidos: mismo total.
    younger = make_socio(db, fecha_nacimiento=date(1980, 3, 15), dni="10000001")
    older = make_socio(db, fecha_nacimiento=date(1980, 1, 2), dni="90000009")

    ranking = run_at(db, admin)

    entries = entries_of(db, ranking)
    assert entries[0].total == entries[1].total
    assert socios_in_order(db, ranking) == [older.id, younger.id]


def test_the_dni_tiebreak_compares_numbers_not_text(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    long_dni = make_socio(db, dni="30000001")
    short_dni = make_socio(db, dni="4000000")

    ranking = run_at(db, admin)

    assert socios_in_order(db, ranking) == [short_dni.id, long_dni.id]


# --- Unitarias: snapshot y posiciones ------------------------------------------------------


def test_the_snapshot_keeps_the_dates_used_by_the_tiebreak(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_socio(
        db,
        fecha_nacimiento=date(1975, 6, 20),
        fecha_alta=date(2012, 4, 1),
        fecha_baja_previa=date(2011, 1, 1),
    )

    ranking = run_at(db, admin)

    [entry] = entries_of(db, ranking)
    assert entry.inputs["membership"]["birth_date"] == "1975-06-20"
    assert entry.inputs["membership"]["seniority_start"] == "2012-04-01"


def test_positions_are_unique_and_consecutive_when_everything_ties(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    for n in range(12):
        make_socio(db, dni=str(20000000 + n))

    ranking = run_at(db, admin)

    entries = entries_of(db, ranking)
    assert len({entry.total for entry in entries}) == 1
    assert [entry.position for entry in entries] == list(range(1, 13))
    assert ranking.population_size == 12


def test_the_order_is_the_same_every_time_the_ranking_is_calculated(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    for n in range(6):
        make_socio(db, dni=str(30000000 - n), fecha_alta=date(2010, 1, 1 + n))

    first = run_at(db, admin)
    second = run_at(db, admin)

    assert socios_in_order(db, first) == socios_in_order(db, second)
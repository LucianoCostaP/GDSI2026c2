"""HU-25, Ciclo 3b: participación institucional (esc. 8, FR-009).

Cada entrada del ranking guarda en `inputs["institutional"]` los eventos institucionales a los
que asistió el socio y los meses de sus actividades recurrentes, dentro de los 365 días previos
a la fecha de cálculo. El tope `Pinst_max` y el puntaje los aplica el motor (Ciclo 0).
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.date_utils import BUENOS_AIRES_TZ, a_hora_buenos_aires
from app.models import Ranking, RankingEntry, Socio, User, utcnow
from app.services import ranking_run_service
from tests.conftest import BOCA_ID, RIVER_ID, Outbox
from tests.hu25_helpers import (
    RUNS,
    headers_for,
    load_attendance,
    make_activity,
    make_event,
    make_socio,
    publish_rules,
)

NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
FEDERATED = "deporte_federado"
SUBCOMMISSION = "subcomision"


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


def ba(year: int, month: int, day: int, hour: int = 20, minute: int = 0) -> datetime:
    """Momento en hora de Buenos Aires."""
    return datetime(year, month, day, hour, minute, tzinfo=BUENOS_AIRES_TZ)


def first_day_of_month(today: date, months_back: int) -> date:
    index = today.year * 12 + (today.month - 1) - months_back
    return date(index // 12, index % 12 + 1, 1)


def run_at(db: Session, admin: User, now: datetime = NOW) -> Ranking:
    return ranking_run_service.start_run(db, admin, BOCA_ID, now=now)


def institutional_of(db: Session, ranking: Ranking, socio: Socio) -> dict[str, Any]:
    entry = db.scalars(
        select(RankingEntry).where(
            RankingEntry.ranking_id == ranking.id, RankingEntry.socio_id == socio.id
        )
    ).one()
    return entry.inputs["institutional"]


def assembly(db: Session, event_id: str, when: datetime, points: int = 40):
    return make_event(
        db,
        id_externo=event_id,
        when=when,
        tipo="Institucional",
        clase=None,
        puntos=points,
    )


# --- Aceptación: "Evento institucional puntúa en el pilar institucional" -------------------


def test_an_assembly_of_40_points_and_three_federated_months_give_70(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    now = utcnow()
    today = a_hora_buenos_aires(now).date()
    socio = make_socio(db)
    held = assembly(db, "EVT-ASAMBLEA", now - timedelta(days=20), 40)
    load_attendance(db, held, [socio])
    # Tres meses calendario completos y ya terminados.
    make_activity(
        db,
        socio,
        tipo=FEDERATED,
        desde=first_day_of_month(today, 3),
        hasta=first_day_of_month(today, 0) - timedelta(days=1),
    )

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 201
    ranking = db.get_one(Ranking, response.json()["id"])
    institutional = institutional_of(db, ranking, socio)
    assert institutional["event_points"] == 40
    assert institutional["activity_months"] == {FEDERATED: 3, SUBCOMMISSION: 0}
    assert institutional["activity_points"] == 30
    assert institutional["points"] == 70


# --- Unitarias: eventos institucionales ----------------------------------------------------


def test_institutional_event_uses_published_points(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    elections = assembly(db, "EVT-ELECCIONES", NOW - timedelta(days=60), 50)
    meeting = assembly(db, "EVT-ASAMBLEA", NOW - timedelta(days=30), 40)
    for held in (elections, meeting):
        load_attendance(db, held, [socio])

    ranking = run_at(db, admin)

    institutional = institutional_of(db, ranking, socio)
    assert institutional["events"] == [
        {"event_id": "EVT-ELECCIONES", "points": 50},
        {"event_id": "EVT-ASAMBLEA", "points": 40},
    ]
    assert institutional["points"] == 90


def test_an_event_the_socio_did_not_attend_gives_no_points(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    other = make_socio(db)
    held = assembly(db, "EVT-ASAMBLEA", NOW - timedelta(days=30), 40)
    load_attendance(db, held, [other])

    ranking = run_at(db, admin)

    assert institutional_of(db, ranking, socio)["points"] == 0
    assert institutional_of(db, ranking, other)["points"] == 40


def test_only_institutional_events_feed_institutional_points(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    match = make_event(db, id_externo="EVT-PARTIDO", when=NOW - timedelta(days=5))
    historical = make_event(
        db,
        id_externo="EVT-HISTORICO",
        when=NOW - timedelta(days=6),
        tipo="Historico",
        clase=None,
        puntos=30,
    )
    for held in (match, historical):
        load_attendance(db, held, [socio])

    ranking = run_at(db, admin)

    assert institutional_of(db, ranking, socio)["points"] == 0


def test_institutional_event_without_published_points_is_ignored(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    held = make_event(
        db,
        id_externo="EVT-SIN-PUNTOS",
        when=NOW - timedelta(days=5),
        tipo="Institucional",
        clase=None,
        puntos=None,
    )
    load_attendance(db, held, [socio])

    ranking = run_at(db, admin)

    assert institutional_of(db, ranking, socio)["points"] == 0


def test_events_that_have_not_happened_yet_are_ignored(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    upcoming = assembly(db, "EVT-PROXIMA", NOW + timedelta(hours=1), 40)
    load_attendance(db, upcoming, [socio])

    ranking = run_at(db, admin)

    assert institutional_of(db, ranking, socio)["points"] == 0


# --- Unitarias: vigencia de 365 días -------------------------------------------------------


def test_records_older_than_365_days_expire(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    # Fecha de cálculo 29/10/2026: la vigencia empieza el 29/10/2025 a las 00:00 (Buenos Aires).
    expired = assembly(db, "EVT-VENCIDO", ba(2025, 10, 28, 23, 30), 50)
    valid = assembly(db, "EVT-VIGENTE", ba(2025, 10, 29, 0, 30), 40)
    for held in (expired, valid):
        load_attendance(db, held, [socio])
    make_activity(
        db, socio, tipo=SUBCOMMISSION, desde=date(2025, 1, 1), hasta=date(2025, 10, 28)
    )

    ranking = run_at(db, admin)

    institutional = institutional_of(db, ranking, socio)
    assert institutional["window_start"] == "2025-10-29"
    assert [e["event_id"] for e in institutional["events"]] == ["EVT-VIGENTE"]
    assert institutional["activity_months"] == {FEDERATED: 0, SUBCOMMISSION: 0}
    assert institutional["points"] == 40


# --- Unitarias: actividades recurrentes ----------------------------------------------------


def test_activity_months_capped_at_12(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    make_activity(
        db, socio, tipo=FEDERATED, desde=date(2024, 1, 1), hasta=date(2026, 10, 29)
    )

    ranking = run_at(db, admin)

    institutional = institutional_of(db, ranking, socio)
    assert institutional["activity_months"][FEDERATED] == 12
    assert institutional["activity_points"] == 120


def test_recurring_points_federated_10_subcommission_15(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    make_activity(
        db, socio, tipo=FEDERATED, desde=date(2026, 8, 1), hasta=date(2026, 9, 30)
    )
    make_activity(
        db, socio, tipo=SUBCOMMISSION, desde=date(2026, 9, 1), hasta=date(2026, 9, 30)
    )

    ranking = run_at(db, admin)

    institutional = institutional_of(db, ranking, socio)
    assert institutional["activity_months"] == {FEDERATED: 2, SUBCOMMISSION: 1}
    assert institutional["activity_points"] == 35


def test_a_month_counts_in_full_for_a_partial_activity(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    make_activity(
        db, socio, tipo=FEDERATED, desde=date(2026, 3, 31), hasta=date(2026, 4, 1)
    )

    ranking = run_at(db, admin)

    assert institutional_of(db, ranking, socio)["activity_months"][FEDERATED] == 2


def test_overlapping_records_do_not_count_a_month_twice(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    make_activity(
        db, socio, tipo=FEDERATED, desde=date(2026, 1, 1), hasta=date(2026, 3, 31)
    )
    make_activity(
        db, socio, tipo=FEDERATED, desde=date(2026, 3, 1), hasta=date(2026, 5, 31)
    )

    ranking = run_at(db, admin)

    assert institutional_of(db, ranking, socio)["activity_months"][FEDERATED] == 5


def test_unknown_activity_types_are_ignored(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    make_activity(
        db, socio, tipo="natacion", desde=date(2026, 8, 1), hasta=date(2026, 9, 30)
    )

    ranking = run_at(db, admin)

    assert institutional_of(db, ranking, socio)["points"] == 0


# --- Unitarias: aislamiento entre clubes ---------------------------------------------------


def test_events_and_activities_of_other_clubs_are_ignored(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)
    # Mismo DNI en otro club: nada de lo suyo cuenta para este socio.
    river_socio = make_socio(db, club_id=RIVER_ID, dni=socio.dni)
    river_event = make_event(
        db,
        id_externo="EVT-RIVER",
        when=NOW - timedelta(days=5),
        tipo="Institucional",
        clase=None,
        puntos=40,
        club_id=RIVER_ID,
    )
    load_attendance(db, river_event, [river_socio])
    make_activity(
        db, river_socio, tipo=FEDERATED, desde=date(2026, 8, 1), hasta=date(2026, 9, 30)
    )

    ranking = run_at(db, admin)

    institutional = institutional_of(db, ranking, socio)
    assert institutional["points"] == 0
    assert institutional["events"] == []


def test_every_entry_keeps_its_own_institutional_inputs(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    active = make_socio(db)
    passive = make_socio(db)
    held = assembly(db, "EVT-ASAMBLEA", NOW - timedelta(days=10), 40)
    load_attendance(db, held, [active])

    ranking = run_at(db, admin)

    assert institutional_of(db, ranking, active)["points"] == 40
    assert institutional_of(db, ranking, passive)["points"] == 0

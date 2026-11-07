"""HU-37: cronograma de habilitación de las olas por la API del Admin."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.date_utils import asegurar_utc
from app.models import (
    AuditLog,
    EventoPendienteDB,
    EventoVisibleDB,
    User,
    WaveSchedule,
    WaveSegmentation,
    utcnow,
)
from app.services import wave_schedule_service
from tests.conftest import BOCA_ID, RIVER_ID, MakeMember, Outbox, bearer, member_token
from tests.hu25_helpers import headers_for, publish_rules
from tests.hu36_helpers import DAY, HOUR, code_of, partido, ranking_with
from tests.hu36_helpers import generate as generate_waves


def schedule_url(event: EventoVisibleDB | str) -> str:
    event_id = event if isinstance(event, str) else event.id_interno
    return f"/admin/events/{event_id}/schedule"


def generate_schedule(
    client: TestClient,
    headers: dict[str, str],
    event: EventoVisibleDB | str,
    *,
    opening: datetime | None = None,
    closing: datetime | None = None,
    confirmed: bool = False,
):
    """Pide el cronograma; por defecto, apertura en 2 días y cierre un día después."""
    opening = opening or utcnow() + 2 * DAY
    closing = closing or opening + DAY
    return client.post(
        schedule_url(event),
        json={
            "opening_at": opening.isoformat(),
            "closing_at": closing.isoformat(),
            "confirmed": confirmed,
        },
        headers=headers,
    )


def as_utc(value: str) -> datetime:
    return asegurar_utc(datetime.fromisoformat(value))


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


def segmented(
    client: TestClient,
    db: Session,
    admin: User,
    headers: dict[str, str],
    *,
    when: datetime | None = None,
) -> EventoVisibleDB:
    """Un Partido de Boca con olas generadas (HU-36) sobre un ranking de 10 socios."""
    ranking_with(db, admin, 10)
    event = partido(db, when=when)
    assert generate_waves(client, headers, event).status_code == 201
    return event


def schedules(db: Session) -> list[WaveSchedule]:
    return list(db.scalars(select(WaveSchedule)))


def audits(db: Session) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.entity == "wave_schedule")
            .order_by(AuditLog.id)
        )
    )


# Escenario 1


def test_without_segmentation_the_schedule_cannot_be_generated(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 10)

    response = generate_schedule(client, boca, partido(db))

    assert response.status_code == 409
    assert code_of(response) == "SEGMENTATION_REQUIRED"


def test_with_segmentation_the_schedule_is_generated_as_draft(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    opening = utcnow() + 2 * DAY
    closing = opening + 5 * HOUR

    response = generate_schedule(client, boca, event, opening=opening, closing=closing)

    assert response.status_code == 201
    body = response.json()
    assert body["event"]["id_interno"] == event.id_interno
    assert body["status"] == "draft"
    assert as_utc(body["opening_at"]) == opening
    assert as_utc(body["closing_at"]) == closing
    assert body["generated_by"] == admin.name
    segmentation = db.scalars(select(WaveSegmentation)).one()
    assert [s.segmentation_id for s in schedules(db)] == [segmentation.id]


def test_the_generated_schedule_can_be_read(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    generated = generate_schedule(client, boca, event).json()

    read = client.get(schedule_url(event), headers=boca)

    assert read.status_code == 200
    assert read.json() == generated


def test_generation_is_audited(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    opening = datetime(2030, 3, 1, 18, 0, tzinfo=UTC)
    closing = opening + 5 * HOUR

    generate_schedule(client, boca, event, opening=opening, closing=closing)

    (generated,) = audits(db)
    assert generated.action == "wave_schedule.generated"
    assert generated.actor_user_id == admin.id
    assert generated.details["event_id"] == event.id_interno
    assert generated.details["new"] == {
        "segmentation_id": db.scalars(select(WaveSegmentation)).one().id,
        "opening_at": "2030-03-01T18:00:00+00:00",
        "closing_at": "2030-03-01T23:00:00+00:00",
    }


# Casos borde: solo Partidos publicados, futuros y del club del Admin


@pytest.mark.parametrize("tipo", ["Institucional", "Historico"])
def test_only_partidos_have_a_schedule(
    client: TestClient, db: Session, admin: User, boca: dict[str, str], tipo: str
) -> None:
    response = generate_schedule(client, boca, partido(db, tipo=tipo))

    assert response.status_code == 409
    assert code_of(response) == "NOT_A_PARTIDO"


def test_a_partido_pending_publication_cannot_get_a_schedule(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    pending = EventoPendienteDB(
        id_interno=f"PEND-{uuid.uuid4().hex[:8]}",
        club_id=BOCA_ID,
        id_externo=f"P-{uuid.uuid4().hex[:8]}",
        titulo="Partido sin publicar",
        fecha_hora=utcnow() + 10 * DAY,
        lugar="La Bombonera",
        tipo="Partido",
    )
    db.add(pending)
    db.commit()

    response = generate_schedule(client, boca, pending.id_interno)

    assert response.status_code == 409
    assert code_of(response) == "EVENT_NOT_PUBLISHED"
    assert "antes de armar el cronograma" in response.json()["detail"]["message"]


def test_a_segmented_partido_that_already_started_cannot_get_a_schedule(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    event.fecha_hora = utcnow() - HOUR
    db.commit()

    response = generate_schedule(client, boca, event)

    assert response.status_code == 409
    assert code_of(response) == "EVENT_ALREADY_STARTED"
    assert response.json()["detail"]["message"] == (
        "El partido ya empezó: no se puede generar el cronograma."
    )


def test_the_start_is_compared_with_the_injected_clock(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    kickoff = datetime(2030, 3, 1, 21, 0, tzinfo=UTC)
    event = segmented(client, db, admin, boca, when=kickoff)
    opening = kickoff - 5 * HOUR

    with pytest.raises(HTTPException) as started:
        wave_schedule_service.generate(
            db,
            admin,
            BOCA_ID,
            event.id_interno,
            opening_at=opening,
            closing_at=kickoff,
            now=kickoff,
        )
    view = wave_schedule_service.generate(
        db,
        admin,
        BOCA_ID,
        event.id_interno,
        opening_at=opening,
        closing_at=kickoff,
        now=kickoff - timedelta(seconds=1),
    )

    assert started.value.status_code == 409
    assert view.schedule.event_id == event.id_interno


def test_an_event_that_does_not_exist_answers_404(
    client: TestClient, boca: dict[str, str]
) -> None:
    response = generate_schedule(client, boca, "NO-EXISTE")

    assert response.status_code == 404
    assert code_of(response) == "EVENT_NOT_FOUND"


def test_an_event_of_another_club_answers_like_one_that_does_not_exist(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    river_event = partido(db, club_id=RIVER_ID)

    generated = generate_schedule(client, boca, river_event)
    read = client.get(schedule_url(river_event), headers=boca)

    assert generated.status_code == 404
    assert code_of(generated) == "EVENT_NOT_FOUND"
    assert read.status_code == 404


def test_nothing_is_stored_or_audited_when_it_is_rejected(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 10)

    generate_schedule(client, boca, partido(db))

    assert schedules(db) == []
    assert audits(db) == []


def test_a_socio_cannot_use_any_schedule_route(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
) -> None:
    member = make_member(activated=True)
    headers = bearer(member_token(client, outbox, member))
    event = partido(db)

    for response in (
        client.get(schedule_url(event), headers=headers),
        generate_schedule(client, headers, event),
    ):
        assert response.status_code == 403

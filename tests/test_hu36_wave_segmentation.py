"""HU-36: generación de las olas de un Partido por la API del Admin (escenarios 1 a 10)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AuditLog,
    EventoPendienteDB,
    RankingState,
    User,
    WaveSchedule,
    WaveScheduleStatus,
    WaveSegmentation,
    utcnow,
)
from app.services import segmentation_service
from tests.conftest import BOCA_ID, RIVER_ID, MakeMember, Outbox, bearer, member_token
from tests.hu25_helpers import (
    headers_for,
    make_ranking,
    make_roster_load,
    publish_rules,
)
from tests.hu36_helpers import (
    DAY,
    HOUR,
    code_of,
    generate,
    partido,
    ranking_with,
    segmentation_url,
)

EVENTS = "/admin/segmentation/events"
PREFLIGHT = "/admin/segmentation/preflight"


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    headers = headers_for(client, outbox, admin)
    publish_rules(client, headers)
    return headers


def audits(db: Session) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.entity == "wave_segmentation")
            .order_by(AuditLog.id)
        )
    )


# Escenario 1


def test_generates_for_a_published_partido_and_stores_the_ranking_used(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking = ranking_with(db, admin, 10)
    event = partido(db)

    response = generate(client, boca, event)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["event"]["id_interno"] == event.id_interno
    assert body["ranking"]["id"] == ranking.id
    assert body["ranking"]["rules_version"] == 1
    assert body["ranked_total"] == 10
    assert body["percentile_step"] == 20
    assert body["generated_by"] == admin.name
    stored = db.scalars(select(WaveSegmentation)).one()
    assert (stored.event_id, stored.ranking_id) == (event.id_interno, ranking.id)


def test_every_generation_is_audited(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking = ranking_with(db, admin, 10)
    event = partido(db)

    generate(client, boca, event)

    [entry] = audits(db)
    assert entry.action == "wave_segmentation.generated"
    assert entry.actor_user_id == admin.id
    assert entry.details["event_id"] == event.id_interno
    assert entry.details["previous"] is None
    assert entry.details["new"] == {
        "ranking_id": ranking.id,
        "ranked_total": 10,
        "percentile_step": 20,
    }


# Escenarios 2 a 5


def test_shows_order_percentile_range_position_range_and_socios_per_wave(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 103)

    response = generate(client, boca, partido(db))

    assert response.json()["waves"] == [
        {
            "order": 1,
            "percentile_from": 0,
            "percentile_to": 20,
            "position_from": 1,
            "position_to": 20,
            "socios": 20,
        },
        {
            "order": 2,
            "percentile_from": 20,
            "percentile_to": 40,
            "position_from": 21,
            "position_to": 41,
            "socios": 21,
        },
        {
            "order": 3,
            "percentile_from": 40,
            "percentile_to": 60,
            "position_from": 42,
            "position_to": 61,
            "socios": 20,
        },
        {
            "order": 4,
            "percentile_from": 60,
            "percentile_to": 80,
            "position_from": 62,
            "position_to": 82,
            "socios": 21,
        },
        {
            "order": 5,
            "percentile_from": 80,
            "percentile_to": 100,
            "position_from": 83,
            "position_to": 103,
            "socios": 21,
        },
    ]


def test_small_rankings_omit_the_empty_bands_and_renumber(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 3)

    waves = generate(client, boca, partido(db)).json()["waves"]

    assert [(w["order"], w["percentile_from"], w["position_from"]) for w in waves] == [
        (1, 20, 1),
        (2, 60, 2),
        (3, 80, 3),
    ]


def test_the_step_comes_from_the_setting_and_is_kept(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ranking_with(db, admin, 8)
    event = partido(db)
    monkeypatch.setattr(settings, "wave_percentile_step", 25)
    generate(client, boca, event)

    monkeypatch.setattr(settings, "wave_percentile_step", 20)
    body = client.get(segmentation_url(event), headers=boca).json()

    assert body["percentile_step"] == 25
    assert [w["socios"] for w in body["waves"]] == [2, 2, 2, 2]


# Escenario 6


@pytest.mark.parametrize("tipo", ["Institucional", "Historico"])
def test_only_partidos_can_be_segmented(
    client: TestClient, db: Session, admin: User, boca: dict[str, str], tipo: str
) -> None:
    ranking_with(db, admin, 5)

    response = generate(client, boca, partido(db, tipo=tipo))

    assert response.status_code == 409
    assert code_of(response) == "NOT_A_PARTIDO"


def test_a_partido_pending_publication_cannot_be_segmented(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 5)
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

    response = generate(client, boca, pending.id_interno)

    assert response.status_code == 409
    assert code_of(response) == "EVENT_NOT_PUBLISHED"


def test_a_partido_that_already_started_cannot_be_segmented(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 5)

    response = generate(client, boca, partido(db, when=utcnow() - HOUR))

    assert response.status_code == 409
    assert code_of(response) == "EVENT_ALREADY_STARTED"


def test_the_start_is_compared_with_the_injected_clock(
    db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 5)
    kickoff = datetime(2030, 3, 1, 21, 0, tzinfo=UTC)
    event = partido(db, when=kickoff)

    with pytest.raises(HTTPException) as started:
        segmentation_service.generate(
            db, admin, BOCA_ID, event.id_interno, confirmed=False, now=kickoff
        )
    assert started.value.detail["code"] == "EVENT_ALREADY_STARTED"

    view, replaced = segmentation_service.generate(
        db,
        admin,
        BOCA_ID,
        event.id_interno,
        confirmed=False,
        now=kickoff - timedelta(seconds=1),
    )
    assert (view.segmentation.ranked_total, replaced) == (5, False)


def test_without_a_completed_ranking_it_cannot_be_segmented(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    make_ranking(db, admin, RankingState.RUNNING)
    make_ranking(db, admin, RankingState.FAILED)

    response = generate(client, boca, partido(db))

    assert response.status_code == 409
    assert code_of(response) == "NO_COMPLETED_RANKING"


def test_a_completed_ranking_without_socios_cannot_be_segmented(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 0)

    response = generate(client, boca, partido(db))

    assert response.status_code == 409
    assert code_of(response) == "RANKING_WITHOUT_SOCIOS"


def test_an_event_that_does_not_exist_answers_404(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 5)

    response = generate(client, boca, "NO-EXISTE")

    assert response.status_code == 404
    assert code_of(response) == "EVENT_NOT_FOUND"


def test_an_event_of_another_club_answers_like_one_that_does_not_exist(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 5)
    river_event = partido(db, club_id=RIVER_ID)

    generated = generate(client, boca, river_event)
    read = client.get(segmentation_url(river_event), headers=boca)

    assert generated.status_code == 404
    assert code_of(generated) == "EVENT_NOT_FOUND"
    assert read.status_code == 404


def test_nothing_is_stored_or_audited_when_it_is_rejected(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    generate(client, boca, partido(db))

    assert db.scalars(select(WaveSegmentation)).all() == []
    assert audits(db) == []


# Escenario 7


def test_regenerating_requires_confirmation(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    first = ranking_with(db, admin, 5)
    event = partido(db)
    generate(client, boca, event)
    ranking_with(db, admin, 10)

    response = generate(client, boca, event, confirmed=False)

    assert response.status_code == 422
    assert code_of(response) == "CONFIRMATION_REQUIRED"
    assert db.scalars(select(WaveSegmentation)).one().ranking_id == first.id


def test_regenerating_with_confirmation_replaces_it_with_the_ranking_in_force(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    first = ranking_with(db, admin, 5, at=utcnow() - 2 * HOUR)
    event = partido(db)
    generate(client, boca, event)
    second = ranking_with(db, admin, 10)

    response = generate(client, boca, event, confirmed=True)

    assert response.status_code == 200
    assert response.json()["ranking"]["id"] == second.id
    assert response.json()["ranked_total"] == 10
    assert len(db.scalars(select(WaveSegmentation)).all()) == 1
    regenerated = audits(db)[-1]
    assert regenerated.action == "wave_segmentation.regenerated"
    assert regenerated.details["previous"] == {
        "ranking_id": first.id,
        "ranked_total": 5,
        "percentile_step": 20,
    }
    assert regenerated.details["new"]["ranking_id"] == second.id


# Escenario 8


def test_after_the_first_wave_opened_it_cannot_be_regenerated(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 5)
    event = partido(db)
    generate(client, boca, event)

    with patch.object(segmentation_service, "first_wave_opened", return_value=True):
        response = generate(client, boca, event, confirmed=True)

    assert response.status_code == 409
    assert code_of(response) == "SEGMENTATION_LOCKED"


def schedule_for(
    db: Session, admin: User, status: WaveScheduleStatus, opening: datetime
) -> WaveSchedule:
    """Un cronograma (HU-37) de las olas ya generadas, con la apertura indicada."""
    segmentation = db.scalars(select(WaveSegmentation)).one()
    schedule = WaveSchedule(
        club_id=BOCA_ID,
        event_id=segmentation.event_id,
        segmentation_id=segmentation.id,
        opening_at=opening,
        closing_at=opening + DAY,
        status=status,
        generated_by_id=admin.id,
    )
    db.add(schedule)
    db.commit()
    return schedule


def test_with_a_confirmed_schedule_already_open_the_waves_are_locked(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    # Sin mock: el bloqueo sale del cronograma confirmado de HU-37.
    ranking_with(db, admin, 5)
    event = partido(db)
    generate(client, boca, event)
    schedule_for(db, admin, WaveScheduleStatus.CONFIRMED, utcnow() - HOUR)

    response = generate(client, boca, event, confirmed=True)

    assert response.status_code == 409
    assert code_of(response) == "SEGMENTATION_LOCKED"


def test_a_draft_schedule_past_its_opening_does_not_lock_the_waves(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 5)
    event = partido(db)
    generate(client, boca, event)
    schedule_for(db, admin, WaveScheduleStatus.DRAFT, utcnow() - HOUR)

    response = generate(client, boca, event, confirmed=True)

    assert response.status_code == 200


def test_regenerating_the_waves_invalidates_the_schedule(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 5)
    event = partido(db)
    generate(client, boca, event)
    schedule = schedule_for(db, admin, WaveScheduleStatus.CONFIRMED, utcnow() + DAY)

    response = generate(client, boca, event, confirmed=True)

    assert response.status_code == 200
    db.refresh(schedule)
    assert schedule.status == WaveScheduleStatus.INVALIDATED


# Escenario 9


def test_a_later_ranking_does_not_change_the_generated_waves(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    first = ranking_with(db, admin, 5, at=utcnow() - 2 * HOUR)
    event = partido(db)
    generated = generate(client, boca, event).json()

    ranking_with(db, admin, 50)
    shown = client.get(segmentation_url(event), headers=boca).json()

    assert shown["ranking"]["id"] == first.id
    assert shown["waves"] == generated["waves"]


# Escenario 10


def test_preflight_warns_about_a_stale_roster_and_loads_after_the_ranking(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 5, at=utcnow() - 3 * DAY)
    make_roster_load(db, completed_at=utcnow() - 2 * DAY)

    response = client.get(PREFLIGHT, headers=boca)

    assert response.status_code == 200
    assert [w["code"] for w in response.json()["warnings"]] == [
        "ROSTER_STALE",
        "LOADS_AFTER_LAST_RANKING",
    ]
    assert response.json()["can_continue"] is True


def test_preflight_is_empty_with_fresh_data(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    make_roster_load(db, completed_at=utcnow() - 3 * HOUR)
    ranking_with(db, admin, 5)

    response = client.get(PREFLIGHT, headers=boca)

    assert response.json()["warnings"] == []


def test_warnings_do_not_block_the_generation(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 5)

    assert client.get(PREFLIGHT, headers=boca).json()["warnings"]
    assert generate(client, boca, partido(db)).status_code == 201


# Lectura y lista de partidos


def test_reading_an_event_without_waves_answers_404(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    response = client.get(segmentation_url(partido(db)), headers=boca)

    assert response.status_code == 404
    assert code_of(response) == "SEGMENTATION_NOT_FOUND"


def test_the_list_has_only_upcoming_published_partidos_of_the_club(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    ranking_with(db, admin, 5)
    later = partido(db, when=utcnow() + 20 * DAY)
    sooner = partido(db, when=utcnow() + 5 * DAY)
    partido(db, when=utcnow() - DAY)
    partido(db, tipo="Institucional")
    partido(db, tipo="Historico")
    partido(db, club_id=RIVER_ID)
    generate(client, boca, later)

    items = client.get(EVENTS, headers=boca).json()

    assert [i["event"]["id_interno"] for i in items] == [
        sooner.id_interno,
        later.id_interno,
    ]
    assert items[0]["segmentation"] is None
    assert items[1]["segmentation"]["waves_count"] == 5


# Acceso


def test_a_socio_cannot_use_any_route(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    make_member: MakeMember,
) -> None:
    member = make_member(activated=True)
    headers = bearer(member_token(client, outbox, member))
    event = partido(db)

    for response in (
        client.get(EVENTS, headers=headers),
        client.get(PREFLIGHT, headers=headers),
        client.get(segmentation_url(event), headers=headers),
        generate(client, headers, event, confirmed=True),
    ):
        assert response.status_code == 403

"""HU-37: cronograma de habilitación de las olas por la API del Admin."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.date_utils import asegurar_utc
from app.models import (
    AuditLog,
    EventoPendienteDB,
    EventoVisibleDB,
    User,
    WaveSchedule,
    WaveScheduleStatus,
    WaveSegmentation,
    utcnow,
)
from app.services import segmentation_service, wave_schedule_service
from tests.conftest import BOCA_ID, RIVER_ID, MakeMember, Outbox, bearer, member_token
from tests.hu25_helpers import headers_for, publish_rules
from tests.hu36_helpers import DAY, HOUR, code_of, partido, ranking_with
from tests.hu36_helpers import generate as generate_waves

MINUTE = timedelta(minutes=1)


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


def confirm_url(event: EventoVisibleDB | str) -> str:
    return f"{schedule_url(event)}/confirm"


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
    socios: int = 10,
) -> EventoVisibleDB:
    """Un Partido de Boca con olas generadas (HU-36); 10 socios dan 5 olas."""
    ranking_with(db, admin, socios)
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
    event = segmented(
        client, db, admin, boca, when=datetime(2030, 3, 2, 21, 0, tzinfo=UTC)
    )
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


# Escenario 2


@pytest.mark.parametrize(
    ("opening_in", "closing_in", "code"),
    [
        (-MINUTE, 3 * DAY, "OPENING_NOT_IN_FUTURE"),
        (3 * DAY, 2 * DAY, "CLOSING_NOT_AFTER_OPENING"),
        (2 * DAY, 2 * DAY, "CLOSING_NOT_AFTER_OPENING"),
        (2 * DAY, 11 * DAY, "CLOSING_AFTER_EVENT_START"),
        (2 * DAY, 2 * DAY + 24 * MINUTE, "WAVE_STEP_TOO_SHORT"),
    ],
)
def test_invalid_periods_are_rejected_with_the_reason(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    opening_in: timedelta,
    closing_in: timedelta,
    code: str,
) -> None:
    event = segmented(client, db, admin, boca, when=utcnow() + 10 * DAY)
    now = utcnow()

    response = generate_schedule(
        client, boca, event, opening=now + opening_in, closing=now + closing_in
    )

    assert response.status_code == 422
    assert code_of(response) == code
    assert response.json()["detail"]["message"]
    assert schedules(db) == []
    assert audits(db) == []


def test_the_step_message_tells_the_minimum_period(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    opening = utcnow() + 2 * DAY

    response = generate_schedule(
        client, boca, event, opening=opening, closing=opening + 10 * MINUTE
    )

    assert response.json()["detail"]["message"] == (
        "Entre oleadas tiene que haber al menos 5 minutos: con 5 oleadas, "
        "el período tiene que durar al menos 25 minutos."
    )


def test_the_minimum_period_uses_the_waves_that_exist(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    # 3 socios dan 3 olas (HU-36 omite las bandas vacías): alcanzan 15 minutos.
    event = segmented(client, db, admin, boca, socios=3)
    opening = utcnow() + 2 * DAY

    response = generate_schedule(
        client, boca, event, opening=opening, closing=opening + 15 * MINUTE
    )

    assert response.status_code == 201


def test_the_minimum_step_comes_from_the_setting(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event = segmented(client, db, admin, boca)
    opening = utcnow() + 2 * DAY
    monkeypatch.setattr(settings, "wave_min_step_minutes", 10)

    response = generate_schedule(
        client, boca, event, opening=opening, closing=opening + 45 * MINUTE
    )

    assert response.status_code == 422
    assert code_of(response) == "WAVE_STEP_TOO_SHORT"


def test_dates_without_time_zone_are_read_in_buenos_aires(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(
        client, db, admin, boca, when=datetime(2030, 3, 2, 21, 0, tzinfo=UTC)
    )

    response = client.post(
        schedule_url(event),
        json={"opening_at": "2030-03-01T15:00", "closing_at": "2030-03-01T20:00"},
        headers=boca,
    )

    assert response.status_code == 201
    assert as_utc(response.json()["opening_at"]) == datetime(
        2030, 3, 1, 18, 0, tzinfo=UTC
    )
    assert as_utc(response.json()["closing_at"]) == datetime(
        2030, 3, 1, 23, 0, tzinfo=UTC
    )


# Escenario 3


def test_waves_start_evenly_spaced_with_wave_1_first(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(
        client, db, admin, boca, when=datetime(2030, 3, 2, 21, 0, tzinfo=UTC)
    )
    opening = datetime(2030, 3, 1, 21, 0, tzinfo=UTC)

    response = generate_schedule(
        client, boca, event, opening=opening, closing=opening + 5 * HOUR
    )

    waves = response.json()["waves"]
    assert [w["order"] for w in waves] == [1, 2, 3, 4, 5]
    assert [as_utc(w["starts_at"]) for w in waves] == [
        opening + hours * HOUR for hours in range(5)
    ]
    assert waves[0]["position_from"] == 1
    assert waves[0]["percentile_from"] == 0
    assert waves[-1]["percentile_to"] == 100


def test_every_wave_gets_a_start_within_the_period(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca, socios=103)
    opening = utcnow() + 2 * DAY
    closing = opening + 7 * HOUR + 13 * MINUTE

    response = generate_schedule(client, boca, event, opening=opening, closing=closing)

    starts = [as_utc(w["starts_at"]) for w in response.json()["waves"]]
    assert len(starts) == 5
    assert starts == sorted(starts)
    assert all(opening <= start < closing for start in starts)


def test_small_rankings_schedule_only_the_existing_waves(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    # 3 socios: HU-36 genera 3 olas (20–40 %, 60–80 % y 80–100 %).
    event = segmented(client, db, admin, boca, socios=3)
    opening = utcnow() + 2 * DAY

    response = generate_schedule(
        client, boca, event, opening=opening, closing=opening + 3 * HOUR
    )

    waves = response.json()["waves"]
    assert [(w["percentile_from"], w["percentile_to"]) for w in waves] == [
        (20, 40),
        (60, 80),
        (80, 100),
    ]
    assert [as_utc(w["starts_at"]) for w in waves] == [
        opening,
        opening + HOUR,
        opening + 2 * HOUR,
    ]


def test_each_wave_shows_its_socios_and_the_general_closing(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca, socios=103)
    opening = utcnow() + 2 * DAY
    closing = opening + 5 * HOUR

    body = generate_schedule(
        client, boca, event, opening=opening, closing=closing
    ).json()

    assert [w["socios"] for w in body["waves"]] == [20, 21, 20, 21, 21]
    assert as_utc(body["closing_at"]) == closing
    assert body["step_seconds"] == 3600
    assert body["min_step_minutes"] == 5


def test_the_schedule_follows_the_waves_of_the_segmentation(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca, socios=103)
    segmentation = client.get(
        f"/admin/events/{event.id_interno}/segmentation", headers=boca
    ).json()

    body = generate_schedule(client, boca, event).json()

    assert [
        {k: v for k, v in w.items() if k not in ("starts_at", "state")}
        for w in body["waves"]
    ] == segmentation["waves"]


# Escenario 4


def test_a_generated_schedule_is_a_draft_that_socios_do_not_see(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)

    body = generate_schedule(client, boca, event).json()

    assert body["status"] == "draft"
    assert body["confirmed_at"] is None
    assert body["confirmed_by"] is None
    assert wave_schedule_service.visible_schedule(db, event.id_interno) is None


def test_reading_an_event_without_schedule_answers_404(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)

    response = client.get(schedule_url(event), headers=boca)

    assert response.status_code == 404
    assert code_of(response) == "SCHEDULE_NOT_FOUND"


def test_confirming_makes_it_visible_to_socios(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    generated = generate_schedule(client, boca, event).json()

    response = client.post(confirm_url(event), headers=boca)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["confirmed_by"] == admin.name
    assert body["confirmed_at"] is not None
    assert [w["starts_at"] for w in body["waves"]] == [
        w["starts_at"] for w in generated["waves"]
    ]
    visible = wave_schedule_service.visible_schedule(db, event.id_interno)
    assert visible is not None
    assert visible.status == WaveScheduleStatus.CONFIRMED
    assert client.get(schedule_url(event), headers=boca).json() == body


def test_confirmation_is_audited(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    generate_schedule(client, boca, event)

    client.post(confirm_url(event), headers=boca)

    generated, confirmed = audits(db)
    assert generated.action == "wave_schedule.generated"
    assert confirmed.action == "wave_schedule.confirmed"
    assert confirmed.actor_user_id == admin.id
    assert confirmed.details["event_id"] == event.id_interno
    assert confirmed.details["new"] == generated.details["new"]


def test_confirming_without_schedule_answers_404(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)

    response = client.post(confirm_url(event), headers=boca)

    assert response.status_code == 404
    assert code_of(response) == "SCHEDULE_NOT_FOUND"


def test_a_confirmed_schedule_cannot_be_confirmed_again(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    generate_schedule(client, boca, event)
    client.post(confirm_url(event), headers=boca)

    response = client.post(confirm_url(event), headers=boca)

    assert response.status_code == 409
    assert code_of(response) == "SCHEDULE_ALREADY_CONFIRMED"
    assert [a.action for a in audits(db)] == [
        "wave_schedule.generated",
        "wave_schedule.confirmed",
    ]


def test_a_draft_whose_opening_passed_cannot_be_confirmed(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    generate_schedule(client, boca, event)
    (draft,) = schedules(db)
    draft.opening_at = utcnow() - MINUTE
    db.commit()

    response = client.post(confirm_url(event), headers=boca)

    assert response.status_code == 409
    assert code_of(response) == "OPENING_ALREADY_PASSED"
    db.refresh(draft)
    assert draft.status == WaveScheduleStatus.DRAFT
    assert wave_schedule_service.visible_schedule(db, event.id_interno) is None


def test_the_opening_is_compared_with_the_injected_clock_when_confirming(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    opening = utcnow() + 2 * DAY
    generate_schedule(client, boca, event, opening=opening)

    with pytest.raises(HTTPException) as passed:
        wave_schedule_service.confirm(db, admin, BOCA_ID, event.id_interno, now=opening)
    view = wave_schedule_service.confirm(
        db, admin, BOCA_ID, event.id_interno, now=opening - timedelta(seconds=1)
    )

    assert passed.value.detail["code"] == "OPENING_ALREADY_PASSED"
    assert view.schedule.status == WaveScheduleStatus.CONFIRMED


def test_a_schedule_of_another_club_cannot_be_confirmed(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    river_event = partido(db, club_id=RIVER_ID)

    response = client.post(confirm_url(river_event), headers=boca)

    assert response.status_code == 404
    assert code_of(response) == "SCHEDULE_NOT_FOUND"


def test_socios_do_not_see_an_invalidated_schedule(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    generate_schedule(client, boca, event)
    client.post(confirm_url(event), headers=boca)
    (schedule,) = schedules(db)
    schedule.status = WaveScheduleStatus.INVALIDATED
    db.commit()

    assert wave_schedule_service.visible_schedule(db, event.id_interno) is None


# Escenario 5


def confirmed_at_2030(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> tuple[EventoVisibleDB, datetime]:
    """Cronograma confirmado de 5 olas: 21:00 a 02:00 UTC (18:00 a 23:00 en Buenos Aires)."""
    event = segmented(
        client, db, admin, boca, when=datetime(2030, 3, 2, 21, 0, tzinfo=UTC)
    )
    opening = datetime(2030, 3, 1, 21, 0, tzinfo=UTC)
    generate_schedule(client, boca, event, opening=opening, closing=opening + 5 * HOUR)
    assert client.post(confirm_url(event), headers=boca).status_code == 200
    return event, opening


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [
        (-MINUTE, ["pending"] * 5),
        (timedelta(0), ["open", "pending", "pending", "pending", "pending"]),
        (2 * HOUR + 30 * MINUTE, ["open", "open", "open", "pending", "pending"]),
        (4 * HOUR, ["open"] * 5),
        (5 * HOUR, ["closed"] * 5),
    ],
)
def test_wave_states_follow_the_server_clock(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    elapsed: timedelta,
    expected: list[str],
) -> None:
    event, opening = confirmed_at_2030(client, db, admin, boca)

    view = wave_schedule_service.get_schedule(
        db, BOCA_ID, event.id_interno, now=opening + elapsed
    )

    assert view.states == expected


def test_a_confirmed_schedule_shows_its_states_through_the_api(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event, _ = confirmed_at_2030(client, db, admin, boca)

    body = client.get(schedule_url(event), headers=boca).json()

    assert [w["state"] for w in body["waves"]] == ["pending"] * 5


def test_a_draft_does_not_open_any_wave(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(
        client, db, admin, boca, when=datetime(2030, 3, 2, 21, 0, tzinfo=UTC)
    )
    opening = datetime(2030, 3, 1, 21, 0, tzinfo=UTC)
    body = generate_schedule(
        client, boca, event, opening=opening, closing=opening + 5 * HOUR
    ).json()

    view = wave_schedule_service.get_schedule(
        db, BOCA_ID, event.id_interno, now=opening + HOUR
    )

    assert [w["state"] for w in body["waves"]] == [None] * 5
    assert view.states == [None] * 5


# Escenario 6


def confirm_schedule(
    client: TestClient, headers: dict[str, str], event: EventoVisibleDB
) -> None:
    assert client.post(confirm_url(event), headers=headers).status_code == 200


@pytest.mark.parametrize("confirm_first", [False, True], ids=["draft", "confirmed"])
def test_regenerating_requires_confirmation(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    confirm_first: bool,
) -> None:
    event = segmented(client, db, admin, boca)
    first = generate_schedule(client, boca, event).json()
    if confirm_first:
        confirm_schedule(client, boca, event)
    opening = utcnow() + 3 * DAY

    response = generate_schedule(client, boca, event, opening=opening)

    assert response.status_code == 422
    assert code_of(response) == "CONFIRMATION_REQUIRED"
    (schedule,) = schedules(db)
    assert as_utc(first["opening_at"]) == asegurar_utc(schedule.opening_at)
    assert "wave_schedule.regenerated" not in [a.action for a in audits(db)]


def test_regenerating_with_confirmation_replaces_the_schedule(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    generate_schedule(client, boca, event)
    opening = utcnow() + 3 * DAY
    closing = opening + 5 * HOUR

    response = generate_schedule(
        client, boca, event, opening=opening, closing=closing, confirmed=True
    )

    assert response.status_code == 200
    assert as_utc(response.json()["opening_at"]) == opening
    assert as_utc(response.json()["closing_at"]) == closing
    assert as_utc(response.json()["waves"][1]["starts_at"]) == opening + HOUR
    (schedule,) = schedules(db)
    assert asegurar_utc(schedule.opening_at) == opening


def test_replacing_a_confirmed_schedule_returns_it_to_draft(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    generate_schedule(client, boca, event)
    confirm_schedule(client, boca, event)

    body = generate_schedule(
        client, boca, event, opening=utcnow() + 3 * DAY, confirmed=True
    ).json()

    assert body["status"] == "draft"
    assert body["confirmed_at"] is None
    assert body["confirmed_by"] is None
    assert [w["state"] for w in body["waves"]] == [None] * 5
    assert wave_schedule_service.visible_schedule(db, event.id_interno) is None


def test_regeneration_is_audited_with_the_previous_period(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(
        client, db, admin, boca, when=datetime(2030, 3, 2, 21, 0, tzinfo=UTC)
    )
    first = datetime(2030, 3, 1, 18, 0, tzinfo=UTC)
    second = datetime(2030, 3, 1, 20, 0, tzinfo=UTC)
    generate_schedule(client, boca, event, opening=first, closing=first + 5 * HOUR)
    confirm_schedule(client, boca, event)

    generate_schedule(
        client, boca, event, opening=second, closing=second + 5 * HOUR, confirmed=True
    )

    regenerated = audits(db)[-1]
    segmentation_id = db.scalars(select(WaveSegmentation)).one().id
    assert regenerated.action == "wave_schedule.regenerated"
    assert regenerated.actor_user_id == admin.id
    assert regenerated.details["previous"] == {
        "status": "confirmed",
        "segmentation_id": segmentation_id,
        "opening_at": "2030-03-01T18:00:00+00:00",
        "closing_at": "2030-03-01T23:00:00+00:00",
    }
    assert regenerated.details["new"] == {
        "segmentation_id": segmentation_id,
        "opening_at": "2030-03-01T20:00:00+00:00",
        "closing_at": "2030-03-02T01:00:00+00:00",
    }


def test_the_new_period_is_validated_like_the_first_one(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    first = generate_schedule(client, boca, event).json()

    response = generate_schedule(
        client, boca, event, opening=utcnow() - MINUTE, confirmed=True
    )

    assert response.status_code == 422
    assert code_of(response) == "OPENING_NOT_IN_FUTURE"
    (schedule,) = schedules(db)
    assert as_utc(first["opening_at"]) == asegurar_utc(schedule.opening_at)


def test_the_first_generation_answers_201_even_with_confirmation(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)

    response = generate_schedule(client, boca, event, confirmed=True)

    assert response.status_code == 201
    assert [a.action for a in audits(db)] == ["wave_schedule.generated"]


# Escenario 7


def open_first_wave(db: Session) -> WaveSchedule:
    """Mueve la apertura del único cronograma un minuto al pasado."""
    (schedule,) = schedules(db)
    schedule.opening_at = utcnow() - MINUTE
    db.commit()
    return schedule


def the_segmentation(db: Session) -> WaveSegmentation:
    return db.scalars(select(WaveSegmentation)).one()


def test_without_schedule_the_first_wave_has_not_opened(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    segmented(client, db, admin, boca)

    assert not segmentation_service.first_wave_opened(
        db, the_segmentation(db), utcnow() + 30 * DAY
    )


def test_a_draft_past_its_opening_has_not_opened_any_wave(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    generate_schedule(client, boca, event)
    open_first_wave(db)

    assert not segmentation_service.first_wave_opened(
        db, the_segmentation(db), utcnow()
    )


def test_the_first_wave_opens_at_the_opening_of_a_confirmed_schedule(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    _, opening = confirmed_at_2030(client, db, admin, boca)
    segmentation = the_segmentation(db)

    assert not segmentation_service.first_wave_opened(
        db, segmentation, opening - timedelta(seconds=1)
    )
    assert segmentation_service.first_wave_opened(db, segmentation, opening)


def test_after_the_first_wave_opened_the_schedule_cannot_be_regenerated(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    generate_schedule(client, boca, event)
    confirm_schedule(client, boca, event)
    schedule = open_first_wave(db)
    opened_at = schedule.opening_at

    response = generate_schedule(
        client, boca, event, opening=utcnow() + 3 * DAY, confirmed=True
    )

    assert response.status_code == 409
    assert code_of(response) == "SCHEDULE_LOCKED"
    db.refresh(schedule)
    assert schedule.opening_at == opened_at
    assert schedule.status == WaveScheduleStatus.CONFIRMED
    assert "wave_schedule.regenerated" not in [a.action for a in audits(db)]


def test_the_lock_uses_the_injected_clock(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event, opening = confirmed_at_2030(client, db, admin, boca)

    with pytest.raises(HTTPException) as locked:
        wave_schedule_service.generate(
            db,
            admin,
            BOCA_ID,
            event.id_interno,
            opening_at=opening + HOUR,
            closing_at=opening + 6 * HOUR,
            confirmed=True,
            now=opening,
        )
    _, replaced = wave_schedule_service.generate(
        db,
        admin,
        BOCA_ID,
        event.id_interno,
        opening_at=opening + HOUR,
        closing_at=opening + 6 * HOUR,
        confirmed=True,
        now=opening - timedelta(seconds=1),
    )

    assert locked.value.detail["code"] == "SCHEDULE_LOCKED"
    assert replaced is True


def test_a_draft_past_its_opening_can_be_regenerated(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event = segmented(client, db, admin, boca)
    generate_schedule(client, boca, event)
    open_first_wave(db)

    response = generate_schedule(
        client, boca, event, opening=utcnow() + 3 * DAY, confirmed=True
    )

    assert response.status_code == 200
    assert response.json()["locked"] is False


def test_the_schedule_reports_whether_it_is_locked(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    event, opening = confirmed_at_2030(client, db, admin, boca)

    before = wave_schedule_service.get_schedule(
        db, BOCA_ID, event.id_interno, now=opening - timedelta(seconds=1)
    )
    after = wave_schedule_service.get_schedule(
        db, BOCA_ID, event.id_interno, now=opening
    )

    assert before.locked is False
    assert after.locked is True
    assert client.get(schedule_url(event), headers=boca).json()["locked"] is False


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
    view, replaced = wave_schedule_service.generate(
        db,
        admin,
        BOCA_ID,
        event.id_interno,
        opening_at=opening,
        closing_at=kickoff,
        now=opening - timedelta(seconds=1),
    )

    assert started.value.status_code == 409
    assert started.value.detail["code"] == "EVENT_ALREADY_STARTED"
    assert view.schedule.event_id == event.id_interno
    assert replaced is False


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
        client.post(confirm_url(event), headers=headers),
    ):
        assert response.status_code == 403

"""HU-25, Ciclo 8: advertencia de datos desactualizados (esc. 7, FR-011).

Antes de calcular, el Admin ve una advertencia si el padrón o las asistencias están viejos o si
hubo cargas después del último ranking. Las advertencias no bloquean el cálculo.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Club, EstadoCargaParticipacion, RankingState, User, utcnow
from app.services import ranking_run_service
from app.services.ranking_preflight_service import (
    ATTENDANCE_STALE,
    LOADS_AFTER_LAST_RANKING,
    ROSTER_STALE,
    PreflightWarning,
    build_preflight,
)
from tests.conftest import BOCA_ID, RIVER_ID, Outbox
from tests.hu25_helpers import (
    RUNS,
    headers_for,
    load_attendance,
    make_activity,
    make_event,
    make_ranking,
    make_roster_load,
    make_socio,
    publish_rules,
    rankings_of,
)

PREFLIGHT = "/admin/ranking/preflight"
NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


@pytest.fixture
def club(db: Session) -> Club:
    return db.get_one(Club, BOCA_ID)


def attendance_load(
    db: Session,
    at: datetime,
    *,
    club_id: uuid.UUID = BOCA_ID,
    estado: EstadoCargaParticipacion = EstadoCargaParticipacion.SUCCESSFUL,
) -> None:
    """Una carga de asistencia que terminó en `at`."""
    event = make_event(
        db, id_externo=f"EVT-{uuid.uuid4().hex[:8]}", when=at - DAY, club_id=club_id
    )
    load_attendance(db, event, [], estado=estado, loaded_at=at)


def fresh_base(db: Session, now: datetime = NOW) -> None:
    """Padrón y asistencias cargados hace 3 horas: dentro de todos los límites."""
    make_roster_load(db, completed_at=now - 3 * HOUR)
    attendance_load(db, now - 3 * HOUR)


def ranking_in_force(db: Session, admin: User, calculated_at: datetime) -> None:
    make_ranking(
        db,
        admin,
        RankingState.COMPLETED,
        calculated_at=calculated_at,
        completed_at=calculated_at,
    )


def codes(warnings: list[PreflightWarning]) -> list[str]:
    return [warning.code for warning in warnings]


# --- Aceptación: "Advertir antes de iniciar" -----------------------------------------------


def test_the_admin_is_warned_about_a_stale_roster_and_can_continue(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    now = utcnow()
    make_roster_load(db, completed_at=now - 25 * HOUR)
    attendance_load(db, now - HOUR)

    preflight = client.get(PREFLIGHT, headers=boca)

    assert preflight.status_code == 200
    body = preflight.json()
    assert [w["code"] for w in body["warnings"]] == ["ROSTER_STALE"]
    assert set(body["warnings"][0]) == {"code", "message", "data_as_of"}
    assert body["can_continue"] is True
    # Y puede continuar: el cálculo no exige haber visto la advertencia.
    assert client.post(RUNS, headers=boca).status_code == 201


def test_the_admin_is_warned_about_loads_after_the_last_ranking_and_can_continue(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    now = utcnow()
    make_roster_load(db, completed_at=now - 3 * HOUR)
    attendance_load(db, now - 3 * HOUR)
    assert client.post(RUNS, headers=boca).status_code == 201
    ranking = ranking_run_service.get_latest_run(db, BOCA_ID)
    assert ranking is not None
    # Una carga que llega después de que empezó el cálculo.
    after = ranking.calculated_at + timedelta(minutes=5)
    attendance_load(db, after)

    body = client.get(PREFLIGHT, headers=boca).json()

    assert [w["code"] for w in body["warnings"]] == ["LOADS_AFTER_LAST_RANKING"]
    assert datetime.fromisoformat(body["warnings"][0]["data_as_of"]) == after
    assert client.post(RUNS, headers=boca).status_code == 201


# --- Unitarias: sin advertencias -----------------------------------------------------------


def test_no_warning_when_fresh(
    client: TestClient, db: Session, admin: User, boca: dict[str, str], club: Club
) -> None:
    publish_rules(client, boca)
    fresh_base(db)
    ranking_in_force(db, admin, NOW - 2 * HOUR)

    assert build_preflight(db, club, NOW) == []


def test_no_ranking_yet_has_no_load_after_warning(db: Session, club: Club) -> None:
    fresh_base(db)

    assert build_preflight(db, club, NOW) == []


def test_a_failed_ranking_is_not_the_one_in_force(
    client: TestClient, db: Session, admin: User, boca: dict[str, str], club: Club
) -> None:
    publish_rules(client, boca)
    fresh_base(db)
    make_ranking(db, admin, RankingState.FAILED, calculated_at=NOW - 6 * HOUR)

    assert build_preflight(db, club, NOW) == []


# --- Unitarias: padrón ---------------------------------------------------------------------


@pytest.mark.parametrize(("hours", "warns"), [(23, False), (24, False), (25, True)])
def test_warns_when_roster_older_than_limit(
    db: Session, club: Club, hours: int, warns: bool
) -> None:
    make_roster_load(db, completed_at=NOW - hours * HOUR)
    attendance_load(db, NOW - HOUR)

    warnings = build_preflight(db, club, NOW)

    assert codes(warnings) == ([ROSTER_STALE] if warns else [])
    if warns:
        assert warnings[0].data_as_of == NOW - hours * HOUR
        assert "24h" in warnings[0].message


def test_a_roster_never_loaded_warns_without_a_date(db: Session, club: Club) -> None:
    attendance_load(db, NOW - HOUR)

    [warning] = build_preflight(db, club, NOW)

    assert warning.code == ROSTER_STALE
    assert warning.data_as_of is None


def test_failed_roster_loads_do_not_count(db: Session, club: Club) -> None:
    make_roster_load(db, completed_at=NOW - HOUR, estado="fallida")
    attendance_load(db, NOW - HOUR)

    assert codes(build_preflight(db, club, NOW)) == [ROSTER_STALE]


# --- Unitarias: asistencias ----------------------------------------------------------------


@pytest.mark.parametrize(("days", "warns"), [(6, False), (7, False), (8, True)])
def test_warns_when_attendance_older_than_limit(
    db: Session, club: Club, days: int, warns: bool
) -> None:
    make_roster_load(db, completed_at=NOW - HOUR)
    attendance_load(db, NOW - days * DAY)

    warnings = build_preflight(db, club, NOW)

    assert codes(warnings) == ([ATTENDANCE_STALE] if warns else [])
    if warns:
        assert warnings[0].data_as_of == NOW - days * DAY
        assert f"{days} días" in warnings[0].message


def test_attendance_never_loaded_warns_without_a_date(db: Session, club: Club) -> None:
    make_roster_load(db, completed_at=NOW - HOUR)

    [warning] = build_preflight(db, club, NOW)

    assert warning.code == ATTENDANCE_STALE
    assert warning.data_as_of is None


def test_only_successful_attendance_loads_count(db: Session, club: Club) -> None:
    make_roster_load(db, completed_at=NOW - HOUR)
    attendance_load(db, NOW - 8 * DAY)
    attendance_load(db, NOW - HOUR, estado=EstadoCargaParticipacion.PENDING_APPROVAL)

    [warning] = build_preflight(db, club, NOW)

    assert warning.code == ATTENDANCE_STALE
    assert warning.data_as_of == NOW - 8 * DAY


def test_activity_loads_do_not_refresh_the_attendance(db: Session, club: Club) -> None:
    make_roster_load(db, completed_at=NOW - HOUR)
    attendance_load(db, NOW - 8 * DAY)
    make_activity(
        db,
        make_socio(db),
        tipo="deporte_federado",
        desde=date(2026, 9, 1),
        hasta=date(2026, 9, 30),
        loaded_at=NOW - HOUR,
    )

    assert codes(build_preflight(db, club, NOW)) == [ATTENDANCE_STALE]


def test_the_attendance_limit_is_configurable(
    db: Session, club: Club, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_roster_load(db, completed_at=NOW - HOUR)
    attendance_load(db, NOW - 3 * DAY)
    assert build_preflight(db, club, NOW) == []

    monkeypatch.setattr(settings, "attendance_freshness_days", 2)

    [warning] = build_preflight(db, club, NOW)
    assert warning.code == ATTENDANCE_STALE
    assert "límite de 2 días" in warning.message


# --- Unitarias: cargas posteriores al último ranking ---------------------------------------


def test_warns_when_load_after_last_ranking(
    client: TestClient, db: Session, admin: User, boca: dict[str, str], club: Club
) -> None:
    publish_rules(client, boca)
    fresh_base(db)
    ranking_in_force(db, admin, NOW - 2 * HOUR)
    attendance_load(db, NOW - HOUR)

    [warning] = build_preflight(db, club, NOW)

    assert warning.code == LOADS_AFTER_LAST_RANKING
    assert warning.data_as_of == NOW - HOUR


@pytest.mark.parametrize("kind", ["roster", "activities"])
def test_roster_and_activity_loads_after_the_ranking_also_warn(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    club: Club,
    kind: str,
) -> None:
    publish_rules(client, boca)
    fresh_base(db)
    ranking_in_force(db, admin, NOW - 2 * HOUR)
    if kind == "roster":
        make_roster_load(db, completed_at=NOW - HOUR)
    else:
        make_activity(
            db,
            make_socio(db),
            tipo="subcomision",
            desde=date(2026, 9, 1),
            hasta=date(2026, 9, 30),
            loaded_at=NOW - HOUR,
        )

    assert codes(build_preflight(db, club, NOW)) == [LOADS_AFTER_LAST_RANKING]


def test_the_latest_load_after_the_ranking_is_reported(
    client: TestClient, db: Session, admin: User, boca: dict[str, str], club: Club
) -> None:
    publish_rules(client, boca)
    fresh_base(db)
    ranking_in_force(db, admin, NOW - 2 * HOUR)
    make_roster_load(db, completed_at=NOW - 90 * timedelta(minutes=1))
    attendance_load(db, NOW - timedelta(minutes=30))

    [warning] = build_preflight(db, club, NOW)

    assert warning.data_as_of == NOW - timedelta(minutes=30)


def test_loads_before_the_ranking_or_unsuccessful_ones_do_not_warn(
    client: TestClient, db: Session, admin: User, boca: dict[str, str], club: Club
) -> None:
    publish_rules(client, boca)
    fresh_base(db)
    ranking_in_force(db, admin, NOW - 2 * HOUR)
    attendance_load(db, NOW - HOUR, estado=EstadoCargaParticipacion.PENDING_APPROVAL)
    make_roster_load(db, completed_at=NOW - HOUR, estado="fallida")

    assert build_preflight(db, club, NOW) == []


# --- Unitarias: aislamiento, orden y bloqueo -----------------------------------------------


def test_loads_of_other_clubs_do_not_count(
    client: TestClient, db: Session, admin: User, boca: dict[str, str], club: Club
) -> None:
    publish_rules(client, boca)
    fresh_base(db)
    ranking_in_force(db, admin, NOW - 2 * HOUR)
    make_roster_load(db, completed_at=NOW - HOUR, club_id=RIVER_ID)
    attendance_load(db, NOW - HOUR, club_id=RIVER_ID)

    assert build_preflight(db, club, NOW) == []


def test_the_freshness_of_another_club_does_not_hide_the_warnings(
    db: Session, club: Club
) -> None:
    make_roster_load(db, completed_at=NOW - HOUR, club_id=RIVER_ID)
    attendance_load(db, NOW - HOUR, club_id=RIVER_ID)

    warnings = build_preflight(db, club, NOW)

    assert codes(warnings) == [ROSTER_STALE, ATTENDANCE_STALE]
    assert [w.data_as_of for w in warnings] == [None, None]


def test_every_warning_is_reported_in_a_fixed_order(
    client: TestClient, db: Session, admin: User, boca: dict[str, str], club: Club
) -> None:
    publish_rules(client, boca)
    make_roster_load(db, completed_at=NOW - 30 * HOUR)
    attendance_load(db, NOW - 10 * DAY)
    ranking_in_force(db, admin, NOW - 40 * HOUR)

    warnings = build_preflight(db, club, NOW)

    # El padrón de hace 30 horas es posterior al ranking de hace 40.
    assert codes(warnings) == [ROSTER_STALE, ATTENDANCE_STALE, LOADS_AFTER_LAST_RANKING]


def test_warning_does_not_block_run(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)

    preflight = client.get(PREFLIGHT, headers=boca).json()

    # Sin ninguna carga: dos advertencias, y el cálculo igual se puede iniciar.
    assert [w["code"] for w in preflight["warnings"]] == [
        "ROSTER_STALE",
        "ATTENDANCE_STALE",
    ]
    assert preflight["can_continue"] is True
    assert rankings_of(db) == []  # consultar las advertencias no calcula nada
    response = client.post(RUNS, headers=boca)
    assert response.status_code == 201
    assert response.json()["status"] == "completed"


def test_the_preflight_requires_authentication(client: TestClient) -> None:
    assert client.get(PREFLIGHT).status_code == 401
"""HU-25, Ciclo 7: fallas durante el cálculo (esc. 5, FR-006, SC-001).

Una falla deja la corrida `failed` con su detalle, no guarda ninguna entrada, no toca el ranking
vigente y se informa al Admin. Una corrida en curso de más de 15 minutos se da por abandonada.
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Ranking, RankingEntry, RankingState, User, utcnow
from app.services import ranking_run_service, ranking_service
from tests.conftest import (
    BOCA_ID,
    RIVER_ID,
    MakeMember,
    Outbox,
    bearer,
    member_token,
)
from tests.hu25_helpers import (
    RUNS,
    adjust_rules,
    entries_of,
    headers_for,
    make_ranking,
    make_socio,
    publish_rules,
)

LATEST = "/admin/ranking/runs/latest"
EXPLANATION = "/member/scoring/explanation"
NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
BREAKDOWN = "se rompió a mitad del cálculo"


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


@pytest.fixture
def socio(
    client: TestClient, outbox: Outbox, make_member: MakeMember
) -> dict[str, str]:
    """Headers de un Socio activado de Boca."""
    headers = bearer(member_token(client, outbox, make_member(activated=True)))
    outbox.clear()
    return headers


def fail_on_call(monkeypatch: pytest.MonkeyPatch, name: str, nth: int) -> None:
    """Hace que `ranking_run_service.<name>` falle en su `nth` llamada (1 = la primera)."""
    real = getattr(ranking_run_service, name)
    calls = {"count": 0}

    def flaky(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == nth:
            raise RuntimeError(BREAKDOWN)
        return real(*args, **kwargs)

    monkeypatch.setattr(ranking_run_service, name, flaky)


def state_of(db: Session, ranking_id: int) -> tuple:
    """Todo lo que importa de un ranking: su fila y sus entradas."""
    ranking = db.get_one(Ranking, ranking_id)
    db.refresh(ranking)
    return (
        ranking.status,
        ranking.completed_at,
        ranking.population_size,
        [(e.socio_id, e.position, e.total, e.inputs) for e in entries_of(db, ranking)],
    )


def latest_run(db: Session) -> Ranking:
    run = ranking_run_service.get_latest_run(db, BOCA_ID)
    assert run is not None
    return run


# --- Aceptación: "Falla a mitad del cálculo" -----------------------------------------------


def test_a_failure_midway_reports_the_error_and_keeps_the_previous_ranking(
    client: TestClient,
    db: Session,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    for _ in range(3):
        make_socio(db)
    previous = client.post(RUNS, headers=boca).json()
    before = state_of(db, previous["id"])
    fail_on_call(monkeypatch, "build_membership_inputs", 2)

    response = client.post(RUNS, headers=boca)

    # Se informa el error, sin mostrar el detalle técnico.
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "RANKING_RUN_FAILED"
    assert detail["message"] == ranking_run_service.RUN_FAILED_MESSAGE
    assert BREAKDOWN not in response.text
    # La corrida queda `failed`.
    failed = latest_run(db)
    assert failed.id == detail["ranking_id"]
    assert failed.status == RankingState.FAILED
    # El ranking anterior sigue vigente, sin cambios.
    in_force = ranking_service.get_ranking_in_force(db, BOCA_ID)
    assert in_force is not None
    assert in_force.id == previous["id"]
    assert state_of(db, previous["id"]) == before


# --- Unitarias: la corrida fallida ---------------------------------------------------------


def test_failure_marks_run_failed_with_error(
    client: TestClient,
    db: Session,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    fail_on_call(monkeypatch, "build_membership_inputs", 1)

    client.post(RUNS, headers=boca)

    failed = latest_run(db)
    assert failed.status == RankingState.FAILED
    assert failed.completed_at is None
    assert failed.population_size == 0
    assert failed.error_message == f"RuntimeError: {BREAKDOWN}"
    latest = client.get(LATEST, headers=boca).json()
    assert latest["status"] == "failed"
    assert latest["completed_at"] is None
    assert latest["error"] == ranking_run_service.RUN_FAILED_MESSAGE


def test_a_completed_run_shows_no_error(
    client: TestClient, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)

    created = client.post(RUNS, headers=boca).json()

    assert created["status"] == "completed"
    assert created["error"] is None


def test_the_failure_is_logged_for_support(
    client: TestClient,
    db: Session,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    fail_on_call(monkeypatch, "build_membership_inputs", 1)

    logger = ranking_run_service.logger
    monkeypatch.setattr(logger, "disabled", False)

    with caplog.at_level(logging.ERROR, logger=ranking_run_service.__name__):
        client.post(RUNS, headers=boca)

    assert "Falló el cálculo del ranking" in caplog.text
    assert BREAKDOWN in caplog.text


def test_the_error_detail_is_truncated() -> None:
    running = Ranking(status=RankingState.RUNNING)

    running.mark_failed("x" * 5000)

    assert running.error_message is not None
    assert len(running.error_message) == 1000


def test_failed_ranking_not_visible_to_members(
    client: TestClient,
    db: Session,
    boca: dict[str, str],
    socio: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    previous = client.post(RUNS, headers=boca).json()
    adjust_rules(client, boca, 1, b_max="10.0")  # reglas v2, todavía sin calcular
    fail_on_call(monkeypatch, "build_membership_inputs", 1)

    assert client.post(RUNS, headers=boca).status_code == 500

    # Para los Socios el ranking vigente sigue siendo el anterior (reglas v1): si vieran la
    # corrida fallida (reglas v2), el aviso de "reglas por reflejar" desaparecería.
    in_force = ranking_service.get_ranking_in_force(db, BOCA_ID)
    assert in_force is not None
    assert in_force.id == previous["id"]
    assert ranking_service.latest_completed_ranking_rules_number(db, BOCA_ID) == 1
    notice = client.get(EXPLANATION, headers=socio).json()["notice"]
    assert notice is not None
    assert notice["code"] == "RULES_AHEAD_OF_RANKING"


def test_a_new_run_is_allowed_after_a_failure(
    client: TestClient,
    db: Session,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    fail_on_call(monkeypatch, "build_membership_inputs", 1)
    assert client.post(RUNS, headers=boca).status_code == 500
    monkeypatch.undo()

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 201
    assert response.json()["status"] == "completed"


# --- Unitarias: el ranking anterior y las entradas -----------------------------------------


def test_failure_leaves_previous_ranking_untouched(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    make_socio(db)
    previous = ranking_run_service.start_run(db, admin, BOCA_ID, now=NOW)
    previous_id = previous.id
    before = state_of(db, previous_id)
    in_force_before = ranking_service.get_ranking_in_force(db, BOCA_ID)
    assert in_force_before is not None
    fail_on_call(monkeypatch, "build_membership_inputs", 2)

    with pytest.raises(HTTPException) as excinfo:
        ranking_run_service.start_run(db, admin, BOCA_ID, now=NOW + timedelta(hours=1))

    assert excinfo.value.status_code == 500
    assert state_of(db, previous_id) == before
    in_force = ranking_service.get_ranking_in_force(db, BOCA_ID)
    assert in_force is not None
    assert in_force.id == in_force_before.id


def test_no_partial_entries_persisted_on_failure(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    make_socio(db)
    ranking_run_service.start_run(db, admin, BOCA_ID, now=NOW)
    entries_before = db.scalar(select(func.count()).select_from(RankingEntry))
    real_commit = db.commit

    def commit_that_breaks_when_completing() -> None:
        completing = any(
            isinstance(obj, Ranking) and obj.status == RankingState.COMPLETED
            for obj in db.dirty
        )
        if completing:
            # Las entradas ya se escribieron dentro de la transacción y falla antes de confirmar.
            db.flush()
            raise RuntimeError("se cortó la conexión antes de confirmar")
        real_commit()

    monkeypatch.setattr(db, "commit", commit_that_breaks_when_completing)

    with pytest.raises(HTTPException):
        ranking_run_service.start_run(db, admin, BOCA_ID, now=NOW + timedelta(hours=1))
    monkeypatch.undo()

    failed = latest_run(db)
    assert failed.status == RankingState.FAILED
    assert entries_of(db, failed) == []
    assert db.scalar(select(func.count()).select_from(RankingEntry)) == entries_before


def test_failure_in_the_middle_of_the_loop_persists_no_entries(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    for _ in range(3):
        make_socio(db)
    fail_on_call(monkeypatch, "build_membership_inputs", 3)

    with pytest.raises(HTTPException):
        ranking_run_service.start_run(db, admin, BOCA_ID, now=NOW)

    assert db.scalar(select(func.count()).select_from(RankingEntry)) == 0
    assert ranking_service.get_ranking_in_force(db, BOCA_ID) is None


def test_marking_a_run_that_is_not_running_as_failed_is_ignored(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    done = make_ranking(db, admin, RankingState.COMPLETED, completed_at=NOW)

    ranking_run_service._mark_failed(db, done.id, "otra falla")

    db.refresh(done)
    assert done.status == RankingState.COMPLETED
    assert done.error_message is None


# --- Unitarias: corridas abandonadas -------------------------------------------------------


def test_running_older_than_15_minutes_is_failed_when_a_new_run_starts(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    abandoned = make_ranking(
        db, admin, RankingState.RUNNING, calculated_at=NOW - timedelta(minutes=16)
    )

    ranking = ranking_run_service.start_run(db, admin, BOCA_ID, now=NOW)

    assert ranking.status == RankingState.COMPLETED
    db.refresh(abandoned)
    assert abandoned.status == RankingState.FAILED
    assert abandoned.completed_at is None
    assert abandoned.error_message == ranking_run_service.ABANDONED_MESSAGE


@pytest.mark.parametrize("minutes", [0, 14, 15])
def test_running_up_to_15_minutes_still_blocks(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    minutes: int,
) -> None:
    publish_rules(client, boca)
    running = make_ranking(
        db, admin, RankingState.RUNNING, calculated_at=NOW - timedelta(minutes=minutes)
    )

    with pytest.raises(HTTPException) as excinfo:
        ranking_run_service.start_run(db, admin, BOCA_ID, now=NOW)

    assert excinfo.value.status_code == 409
    db.refresh(running)
    assert running.status == RankingState.RUNNING


def test_status_endpoint_gives_up_an_abandoned_run(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_ranking(
        db,
        admin,
        RankingState.RUNNING,
        calculated_at=utcnow() - timedelta(minutes=16),
    )

    latest = client.get(LATEST, headers=boca).json()

    assert latest["status"] == "failed"
    assert latest["error"] == ranking_run_service.RUN_FAILED_MESSAGE
    assert client.post(RUNS, headers=boca).status_code == 201


def test_giving_up_runs_only_touches_old_running_runs_of_the_own_club(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    old = NOW - timedelta(minutes=16)
    river = make_ranking(
        db, admin, RankingState.RUNNING, club_id=RIVER_ID, calculated_at=old
    )
    completed = make_ranking(
        db, admin, RankingState.COMPLETED, calculated_at=old, completed_at=old
    )

    assert ranking_run_service.fail_abandoned_runs(db, BOCA_ID, NOW) == 0
    db.refresh(river)
    db.refresh(completed)
    assert river.status == RankingState.RUNNING
    assert completed.status == RankingState.COMPLETED

    assert ranking_run_service.fail_abandoned_runs(db, RIVER_ID, NOW) == 1
    db.refresh(river)
    assert river.status == RankingState.FAILED

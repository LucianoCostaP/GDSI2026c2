"""HU-25, Ciclo 5: una sola corrida a la vez e informar el progreso (esc. 2, FR-001, FR-003).

El cálculo es síncrono, pero la corrida se registra y se confirma como `running` antes de
calcular: así se ve desde afuera, y un segundo pedido se rechaza con 409.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Ranking, RankingEntry, RankingState, User

from app.services import ranking_run_service
from tests.conftest import BOCA_ID, RIVER_ID, Outbox
from tests.hu25_helpers import (
    RUNS,
    headers_for,
    make_ranking,
    make_socio,
    publish_rules,
    rankings_of,
)

LATEST = "/admin/ranking/runs/latest"
NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


def insert_run(
    db: Session, admin: User, state: RankingState, *, club_id=BOCA_ID
) -> Ranking:
    """Una corrida ya guardada en ese estado (como la dejaría otro pedido)."""
    return make_ranking(
        db,
        admin,
        state,
        club_id=club_id,
        completed_at=NOW if state == RankingState.COMPLETED else None,
    )


def error_code(response) -> str:
    return str(response.json()["detail"]["code"])


# --- Aceptación: "Segunda ejecución mientras hay una en curso" -----------------------------


def test_second_run_rejected_with_409_and_code(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    running = insert_run(db, admin, RankingState.RUNNING)

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 409
    assert error_code(response) == "RANKING_RUN_IN_PROGRESS"
    assert response.json()["detail"]["ranking_id"] == running.id
    assert [r.id for r in rankings_of(db)] == [running.id]


# --- Aceptación: "Consultar el progreso" ---------------------------------------------------


def test_status_endpoint_reports_running(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    running = insert_run(db, admin, RankingState.RUNNING)

    response = client.get(LATEST, headers=boca)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == running.id
    assert body["status"] == "running"
    assert body["completed_at"] is None


# --- Unitarias: cuándo se puede correr -----------------------------------------------------


@pytest.mark.parametrize("state", [RankingState.COMPLETED, RankingState.FAILED])
def test_run_allowed_after_previous_completed_or_failed(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    state: RankingState,
) -> None:
    publish_rules(client, boca)
    insert_run(db, admin, state)
    make_socio(db)

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 201
    assert response.json()["status"] == "completed"
    assert ranking_run_service.get_running_run(db, BOCA_ID) is None


def test_running_does_not_affect_other_clubs(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    insert_run(db, admin, RankingState.RUNNING, club_id=RIVER_ID)

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 201
    assert ranking_run_service.get_running_run(db, RIVER_ID) is not None


def test_a_completed_run_leaves_nothing_running(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)

    client.post(RUNS, headers=boca)

    assert ranking_run_service.get_running_run(db, BOCA_ID) is None
    latest = ranking_run_service.get_latest_run(db, BOCA_ID)
    assert latest is not None
    assert latest.status == RankingState.COMPLETED


# --- Unitarias: concurrencia ---------------------------------------------------------------


def test_database_allows_only_one_running_ranking_per_club(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    first = insert_run(db, admin, RankingState.RUNNING)

    db.add(
        Ranking(
            club_id=BOCA_ID,
            rules_version_id=first.rules_version_id,
            status=RankingState.RUNNING,
            calculation_date=NOW.date(),
            calculated_at=NOW,
            population_size=0,
            requested_by_id=admin.id,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    assert len(rankings_of(db)) == 1


def test_concurrent_start_only_one_wins(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    winner = insert_run(db, admin, RankingState.RUNNING)
    # Carrera: el segundo pedido ya miró y no vio ninguna corrida; lo frena el índice único.
    monkeypatch.setattr(ranking_run_service, "get_running_run", lambda *_: None)

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 409
    assert error_code(response) == "RANKING_RUN_IN_PROGRESS"
    assert [r.id for r in rankings_of(db)] == [winner.id]


def test_the_run_is_committed_as_running_before_calculating(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    events: list[str] = []
    real_commit = db.commit
    real_loader = ranking_run_service.load_loaded_matches

    def spy_commit() -> None:
        events.append("commit")
        real_commit()

    def spy_loader(*args, **kwargs):
        events.append("calculating")
        return real_loader(*args, **kwargs)

    monkeypatch.setattr(db, "commit", spy_commit)
    monkeypatch.setattr(ranking_run_service, "load_loaded_matches", spy_loader)

    ranking_run_service.start_run(db, admin, BOCA_ID, now=NOW)

    # Primero se confirma la corrida en curso; recién después se calcula.
    assert events[0] == "commit"
    assert events.index("calculating") > events.index("commit")


# --- Unitarias: una falla no bloquea al club -----------------------------------------------


def test_a_failure_leaves_the_run_failed_and_releases_the_club(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    make_socio(db)

    def broken(*_args, **_kwargs):
        raise RuntimeError("falló la fuente de datos")

    monkeypatch.setattr(ranking_run_service, "load_loaded_matches", broken)
    with pytest.raises(HTTPException) as excinfo:
        ranking_run_service.start_run(db, admin, BOCA_ID, now=NOW)
    assert excinfo.value.status_code == 500
    monkeypatch.undo()

    failed = ranking_run_service.get_latest_run(db, BOCA_ID)
    assert failed is not None
    assert failed.status == RankingState.FAILED
    assert failed.completed_at is None
    assert db.scalars(select(RankingEntry)).all() == []
    assert ranking_run_service.get_running_run(db, BOCA_ID) is None
    assert client.post(RUNS, headers=boca).status_code == 201


def test_only_a_running_ranking_can_fail() -> None:
    running = Ranking(status=RankingState.RUNNING)
    running.mark_failed("falló")

    assert running.status == RankingState.FAILED
    assert running.completed_at is None
    for state in (RankingState.COMPLETED, RankingState.FAILED):
        with pytest.raises(ValueError):
            Ranking(status=state).mark_failed("falló")


# --- Unitarias: endpoint de estado ---------------------------------------------------------


def test_status_endpoint_reports_the_latest_run(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    insert_run(db, admin, RankingState.COMPLETED)
    newest = insert_run(db, admin, RankingState.RUNNING)

    response = client.get(LATEST, headers=boca)

    assert response.json()["id"] == newest.id
    assert response.json()["status"] == "running"


def test_status_endpoint_reports_since_when_a_completed_ranking_is_in_force(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    created = client.post(RUNS, headers=boca).json()

    response = client.get(LATEST, headers=boca)

    assert response.status_code == 200
    assert response.json() == created
    assert response.json()["status"] == "completed"
    assert response.json()["completed_at"] is not None


def test_status_endpoint_without_runs_is_404(
    client: TestClient, boca: dict[str, str]
) -> None:
    response = client.get(LATEST, headers=boca)

    assert response.status_code == 404
    assert error_code(response) == "NO_RANKING_RUN"


def test_status_endpoint_does_not_show_other_clubs(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    insert_run(db, admin, RankingState.COMPLETED, club_id=RIVER_ID)

    response = client.get(LATEST, headers=boca)

    assert response.status_code == 404


def test_status_endpoint_requires_authentication(client: TestClient) -> None:
    assert client.get(LATEST).status_code == 401
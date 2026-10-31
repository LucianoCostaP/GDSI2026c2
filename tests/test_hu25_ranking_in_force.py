"""HU-25, Ciclo 6: finalización y reemplazo atómico (esc. 3 y 4, FR-004, FR-005, FR-010).

El ranking vigente de un club es su última corrida completada; `completed_at` es desde cuándo
rige. Las corridas anteriores se conservan, pero los Socios solo ven el vigente.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ranking, RankingEntry, RankingState, User
from app.services import formula_service, ranking_run_service, ranking_service
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
    rankings_of,
)

EXPLANATION = "/member/scoring/explanation"
LATEST = "/admin/ranking/runs/latest"
NOW = datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
NOTICE = {
    "code": "RULES_AHEAD_OF_RANKING",
    "message": formula_service.RULES_AHEAD_OF_RANKING_NOTICE,
}


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


def republish(client: TestClient, boca: dict[str, str], version: int) -> None:
    """Ajusta los parámetros de las reglas actualmente vigentes."""
    adjust_rules(client, boca, version, b_max="10.0")


# --- Aceptación: "Un ranking nuevo reemplaza al anterior" ----------------------------------


def test_a_new_ranking_replaces_the_previous_one(
    client: TestClient,
    db: Session,
    boca: dict[str, str],
    socio: dict[str, str],
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    first = client.post(RUNS, headers=boca).json()
    republish(client, boca, 1)

    second = client.post(RUNS, headers=boca).json()

    # El Admin ve que se completó y desde cuándo rige.
    assert second["status"] == "completed"
    assert second["completed_at"] is not None
    assert second["completed_at"] >= first["completed_at"]
    assert client.get(LATEST, headers=boca).json() == second
    # Los Socios solo ven el ranking nuevo: el vigente es el que usó las reglas actuales.
    in_force = ranking_service.get_ranking_in_force(db, BOCA_ID)
    assert in_force is not None
    assert in_force.id == second["id"]
    assert second["rules_version"] == 2
    assert client.get(EXPLANATION, headers=socio).json()["notice"] is None


# --- Integración sin mocks de HU-13 (escenarios 5 y 7) -------------------------------------


def test_the_rules_notice_follows_the_ranking_in_force(
    client: TestClient,
    db: Session,
    boca: dict[str, str],
    socio: dict[str, str],
) -> None:
    publish_rules(client, boca)
    # Escenario 7: sin ranking completado no hay aviso.
    assert client.get(EXPLANATION, headers=socio).json()["notice"] is None

    client.post(RUNS, headers=boca)
    # El ranking usó las reglas vigentes: sin aviso.
    assert client.get(EXPLANATION, headers=socio).json()["notice"] is None

    # Escenario 5: las reglas cambian después del último ranking.
    republish(client, boca, 1)
    assert client.get(EXPLANATION, headers=socio).json()["notice"] == NOTICE

    # Un nuevo cálculo las refleja y el aviso desaparece.
    client.post(RUNS, headers=boca)
    assert client.get(EXPLANATION, headers=socio).json()["notice"] is None


def test_the_rules_notice_ignores_running_and_failed_rankings(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    socio: dict[str, str],
) -> None:
    publish_rules(client, boca)
    make_ranking(db, admin, RankingState.FAILED)
    make_ranking(db, admin, RankingState.RUNNING)
    republish(client, boca, 1)

    body = client.get(EXPLANATION, headers=socio).json()

    assert body["notice"] is None
    assert ranking_service.latest_completed_ranking_rules_number(db, BOCA_ID) is None


# --- Unitarias: ranking vigente ------------------------------------------------------------


def test_members_see_only_completed_rankings(
    db: Session, client: TestClient, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    at = NOW
    make_ranking(db, admin, RankingState.COMPLETED, completed_at=at)
    newest_completed = make_ranking(
        db, admin, RankingState.COMPLETED, completed_at=at + timedelta(hours=1)
    )
    make_ranking(db, admin, RankingState.FAILED, calculated_at=at + timedelta(hours=2))
    make_ranking(db, admin, RankingState.RUNNING, calculated_at=at + timedelta(hours=3))

    in_force = ranking_service.get_ranking_in_force(db, BOCA_ID)

    assert in_force is not None
    assert in_force.id == newest_completed.id


def test_without_a_completed_ranking_there_is_none_in_force(
    db: Session, client: TestClient, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_ranking(db, admin, RankingState.FAILED)
    make_ranking(db, admin, RankingState.RUNNING)

    assert ranking_service.get_ranking_in_force(db, BOCA_ID) is None
    assert ranking_service.latest_completed_ranking_rules_number(db, BOCA_ID) is None


def test_the_newest_run_wins_when_two_completed_at_the_same_moment(
    db: Session, client: TestClient, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_ranking(db, admin, RankingState.COMPLETED, completed_at=NOW)
    newer = make_ranking(db, admin, RankingState.COMPLETED, completed_at=NOW)

    in_force = ranking_service.get_ranking_in_force(db, BOCA_ID)

    assert in_force is not None
    assert in_force.id == newer.id


def test_the_ranking_of_another_club_is_not_in_force(
    db: Session, client: TestClient, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_ranking(db, admin, RankingState.COMPLETED, club_id=RIVER_ID, completed_at=NOW)

    assert ranking_service.get_ranking_in_force(db, BOCA_ID) is None
    assert ranking_service.get_ranking_in_force(db, RIVER_ID) is not None


def test_latest_completed_ranking_rules_number_returns_used_version(
    db: Session, client: TestClient, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    client.post(RUNS, headers=boca)
    republish(client, boca, 1)

    # Las reglas ya son la versión 2, pero el último ranking usó la 1.
    assert ranking_service.latest_completed_ranking_rules_number(db, BOCA_ID) == 1
    client.post(RUNS, headers=boca)
    assert ranking_service.latest_completed_ranking_rules_number(db, BOCA_ID) == 2
    assert ranking_service.latest_completed_ranking_rules_number(db, RIVER_ID) is None


# --- Unitarias: desde cuándo rige y atomicidad ---------------------------------------------


def test_completed_at_is_in_force_since(
    db: Session,
    client: TestClient,
    admin: User,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    finished_at = NOW + timedelta(minutes=10)
    monkeypatch.setattr(ranking_run_service, "utcnow", lambda: finished_at)

    ranking = ranking_run_service.start_run(db, admin, BOCA_ID, now=NOW)

    # Rige desde que termina el cálculo, no desde que empezó.
    assert ranking.calculated_at == NOW
    assert ranking.completed_at == finished_at
    in_force = ranking_service.get_ranking_in_force(db, BOCA_ID)
    assert in_force is not None
    assert in_force.id == ranking.id
    assert in_force.completed_at == finished_at


def test_swap_is_atomic_in_single_transaction(
    db: Session,
    client: TestClient,
    admin: User,
    boca: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    make_socio(db)
    previous = ranking_run_service.start_run(db, admin, BOCA_ID, now=NOW)
    previous_id = previous.id
    commits: list[tuple[int, bool]] = []
    in_force_while_calculating: list[int] = []
    real_commit = db.commit
    real_loader = ranking_run_service.load_loaded_matches

    def spy_commit() -> None:
        pending_entries = sum(isinstance(obj, RankingEntry) for obj in db.new)
        completing = any(
            isinstance(obj, Ranking) and obj.status == RankingState.COMPLETED
            for obj in db.dirty
        )
        commits.append((pending_entries, completing))
        real_commit()

    def spy_loader(*args, **kwargs):
        in_force = ranking_service.get_ranking_in_force(db, BOCA_ID)
        assert in_force is not None
        in_force_while_calculating.append(in_force.id)
        return real_loader(*args, **kwargs)

    monkeypatch.setattr(db, "commit", spy_commit)
    monkeypatch.setattr(ranking_run_service, "load_loaded_matches", spy_loader)

    new = ranking_run_service.start_run(db, admin, BOCA_ID, now=NOW)

    # Mientras se calcula sigue vigente el ranking anterior.
    assert in_force_while_calculating == [previous_id]
    # Dos confirmaciones: reclamar la corrida y, juntas, las dos entradas y su finalización.
    assert commits == [(0, False), (2, True)]
    in_force = ranking_service.get_ranking_in_force(db, BOCA_ID)
    assert in_force is not None
    assert in_force.id == new.id


def test_previous_rankings_are_kept_with_their_entries(
    db: Session, client: TestClient, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    make_socio(db)
    client.post(RUNS, headers=boca)
    [first] = rankings_of(db)

    def snapshot(ranking: Ranking) -> list[tuple]:
        return [(e.socio_id, e.position, e.total) for e in entries_of(db, ranking)]

    before = snapshot(first)

    client.post(RUNS, headers=boca)

    rankings = rankings_of(db)
    assert len(rankings) == 2
    assert {r.status for r in rankings} == {RankingState.COMPLETED}
    assert snapshot(first) == before
    assert len(before) == 2
    assert all(len(entries_of(db, r)) == 2 for r in rankings)

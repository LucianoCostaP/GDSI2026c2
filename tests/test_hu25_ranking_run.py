"""HU-25, Ciclo 1: el Admin ejecuta el cálculo y se genera un ranking (escenario 1)."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.date_utils import asegurar_utc
from app.models import (
    Ranking,
    RankingEntry,
    RankingState,
    RulesVersion,
    RulesVersionState,
    User,
)
from app.scoring.components import COMPONENT_KEYS
from app.services import ranking_run_service
from tests.conftest import (
    BOCA_ID,
    RIVER_ID,
    MakeAdmin,
    MakeMember,
    Outbox,
    bearer,
    member_token,
)
from tests.hu25_helpers import (
    RUNS,
    entries_of,
    headers_for,
    make_socio,
    publish_rules,
    rankings_of,
)


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)

# --- Aceptación (escenario 1): el Admin dispara el cálculo --------------------------------


def test_admin_runs_the_calculation_and_a_completed_ranking_is_created(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socio = make_socio(db)

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["rules_version"] == 1
    assert body["population_size"] == 1
    assert body["completed_at"] is not None

    [ranking] = rankings_of(db)
    rules = db.scalars(
        select(RulesVersion).where(
            RulesVersion.club_id == BOCA_ID,
            RulesVersion.state == RulesVersionState.IN_FORCE,
        )
    ).one()
    assert ranking.status == RankingState.COMPLETED
    assert ranking.rules_version_id == rules.id

    [entry] = entries_of(db, ranking)
    assert entry.socio_id == socio.id
    assert entry.position == 1
    assert {key: getattr(entry, key) for key in COMPONENT_KEYS} == {
        key: Decimal("0.00") for key in COMPONENT_KEYS
    }
    assert entry.total == Decimal("0.00")


# --- Unitarias: permisos y club ------------------------------------------------------------


def test_a_member_cannot_run_the_calculation(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    headers = bearer(member_token(client, outbox, member))

    response = client.post(RUNS, headers=headers)

    assert response.status_code == 403
    assert rankings_of(db) == []


def test_running_the_calculation_requires_authentication(
    client: TestClient, db: Session
) -> None:
    response = client.post(RUNS)

    assert response.status_code == 401
    assert rankings_of(db) == []


def test_an_admin_without_club_is_rejected(
    client: TestClient, outbox: Outbox, make_admin: MakeAdmin
) -> None:
    headers = headers_for(client, outbox, make_admin(None))

    response = client.post(RUNS, headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "ADMIN_WITHOUT_CLUB"


def test_the_club_comes_from_the_account_and_not_from_the_request(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    own = make_socio(db, club_id=BOCA_ID)
    make_socio(db, club_id=RIVER_ID)

    response = client.post(
        RUNS,
        params={"club_id": str(RIVER_ID)},
        json={"club_id": str(RIVER_ID)},
        headers={**boca, "X-Club-ID": str(RIVER_ID)},
    )

    assert response.status_code == 201
    assert rankings_of(db, RIVER_ID) == []
    [ranking] = rankings_of(db, BOCA_ID)
    assert [entry.socio_id for entry in entries_of(db, ranking)] == [own.id]


# --- Unitarias: reglas en vigor ------------------------------------------------------------


def test_the_calculation_requires_rules_in_force(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    make_socio(db)

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "FORMULA_NOT_PUBLISHED"
    assert rankings_of(db) == []


def test_the_ranking_records_the_rules_version_in_force_when_it_started(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)

    response = client.post(RUNS, headers=boca)

    assert response.json()["rules_version"] == 1


# --- Unitarias: instantánea de la fecha de cálculo -----------------------------------------


def test_the_cutoff_date_is_the_buenos_aires_date_of_the_injected_clock(
    client: TestClient, db: Session, admin: User, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    # 01:30 UTC del 29/10 son las 22:30 del 28/10 en Buenos Aires.
    moment = datetime(2026, 10, 29, 1, 30, tzinfo=UTC)

    ranking = ranking_run_service.start_run(db, admin, BOCA_ID, now=moment)

    assert ranking.calculation_date == date(2026, 10, 28)
    assert asegurar_utc(ranking.calculated_at) == moment


# --- Unitarias: entradas y posiciones ------------------------------------------------------


def test_every_socio_gets_one_entry_with_a_unique_position(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)
    socios = [make_socio(db) for _ in range(3)]

    client.post(RUNS, headers=boca)

    [ranking] = rankings_of(db)
    entries = entries_of(db, ranking)
    assert ranking.population_size == 3
    assert {entry.socio_id for entry in entries} == {socio.id for socio in socios}
    assert [entry.position for entry in entries] == [1, 2, 3]


def test_a_club_without_socios_gets_an_empty_completed_ranking(
    client: TestClient, db: Session, boca: dict[str, str]
) -> None:
    publish_rules(client, boca)

    response = client.post(RUNS, headers=boca)

    assert response.status_code == 201
    assert response.json()["population_size"] == 0
    [ranking] = rankings_of(db)
    assert entries_of(db, ranking) == []
    assert db.scalar(select(func.count()).select_from(RankingEntry)) == 0


# --- Unitarias: estados de la corrida ------------------------------------------------------


def test_completing_a_running_ranking_sets_its_state_and_the_in_force_since_time() -> None:
    ranking = Ranking(status=RankingState.RUNNING)
    moment = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)

    ranking.mark_completed(moment)

    assert ranking.status == RankingState.COMPLETED
    assert ranking.completed_at == moment


@pytest.mark.parametrize("state", [RankingState.COMPLETED, RankingState.FAILED])
def test_only_a_running_ranking_can_be_completed(state: RankingState) -> None:
    ranking = Ranking(status=state)

    with pytest.raises(ValueError):
        ranking.mark_completed(datetime(2026, 10, 29, 12, 0, tzinfo=UTC))

    assert ranking.status == state
    assert ranking.completed_at is None
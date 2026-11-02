"""HU-18: simulador de puntaje por asistencia (`docs/contrato-api-simulador.md`)."""

import uuid
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RankingEntry, RulesVersion, Socio, User, utcnow
from app.scoring.engine import ScoringParameters, calculate_score
from app.scoring.snapshot import scoring_inputs_from_snapshot
from app.services import ranking_service
from tests.conftest import (
    BOCA_ID,
    RIVER_ID,
    MakeMember,
    Outbox,
    bearer,
    member_token,
)
from tests.hu25_helpers import RUNS, headers_for, make_event, make_socio, publish_rules

URL = "/member/scoring/simulator/{}"


@pytest.fixture
def boca(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    return headers_for(client, outbox, admin)


@pytest.fixture
def account(client: TestClient, outbox: Outbox, db: Session, make_member: MakeMember):
    """Crea un socio del padrón con su cuenta activada y devuelve `(socio, headers)`."""

    def make(*, club_id: uuid.UUID = BOCA_ID, **socio_fields) -> tuple[Socio, dict]:
        dni = socio_fields.pop("dni", str(uuid.uuid4().int)[:8])
        member = make_member(activated=True, dni=dni, club_id=club_id)
        socio = make_socio(db, club_id=club_id, dni=dni, **socio_fields)
        headers = bearer(member_token(client, outbox, member))
        outbox.clear()
        return socio, headers

    return make


def run(client: TestClient, headers: dict[str, str]) -> None:
    response = client.post(RUNS, headers=headers)
    assert response.status_code == 201, response.text


def entry_of(db: Session, socio: Socio) -> RankingEntry:
    ranking = ranking_service.get_ranking_in_force(db, socio.club_id)
    assert ranking is not None
    return db.scalars(
        select(RankingEntry).where(
            RankingEntry.ranking_id == ranking.id, RankingEntry.socio_id == socio.id
        )
    ).one()


def official_total(db: Session, entry: RankingEntry, **changes) -> str:
    """El motor único sobre la instantánea de la entrada, con los cambios indicados."""
    ranking = ranking_service.get_ranking_in_force(db, BOCA_ID)
    assert ranking is not None
    rules = db.get(RulesVersion, ranking.rules_version_id)
    assert rules is not None
    inputs = replace(scoring_inputs_from_snapshot(entry.inputs), **changes)
    total = calculate_score(inputs, ScoringParameters.from_values(rules.values)).total
    return f"{total:.2f}"


def upcoming(db: Session, id_externo: str, **fields):
    return make_event(
        db, id_externo=id_externo, when=utcnow() + timedelta(days=7), **fields
    )


# --- Escenario 1: se elige un evento y se simula solo ese -----------------------------------


def test_selecting_a_partido_starts_its_simulation(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)
    event = upcoming(db, "P-1", clase="B")

    response = client.get(URL.format(event.id_interno), headers=headers)

    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    entry = entry_of(db, socio)
    assert body["event"]["id"] == event.id_interno
    assert body["event"]["tipo"] == "Partido"
    assert body["event"]["puntos"] is None
    assert "clase" not in body["event"]
    assert body["ranking"]["rules_version"] == 1
    assert body["current"] == {
        "score": f"{entry.total:.2f}",
        "position": entry.position,
        "ranked_total": 1,
    }
    assert body["attend"]["score"] == official_total(
        db,
        entry,
        matches_by_class={"A": 0, "B": 1, "C": 0},
        attended_by_class={"A": 0, "B": 1, "C": 0},
    )
    assert body["not_attend"]["score"] == official_total(
        db,
        entry,
        matches_by_class={"A": 0, "B": 1, "C": 0},
    )
    for hypothesis in ("attend", "not_attend"):
        expected = Decimal(body[hypothesis]["score"]) - entry.total
        assert body[hypothesis]["difference"] == f"{expected:.2f}"
        assert body[hypothesis]["position"] is None
    assert body["position_estimate"]["code"] == "POSITION_NOT_AVAILABLE"


def test_the_simulation_covers_only_the_selected_event(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)
    selected = upcoming(db, "P-1", clase="C")
    upcoming(db, "P-2", clase="A")
    upcoming(db, "I-1", tipo="Institucional", clase=None, puntos=40)

    body = client.get(URL.format(selected.id_interno), headers=headers).json()

    # Solo el Partido elegido (clase C): ni el otro Partido ni los puntos institucionales.
    entry = entry_of(db, socio)
    assert body["attend"]["score"] == official_total(
        db,
        entry,
        matches_by_class={"A": 0, "B": 0, "C": 1},
        attended_by_class={"A": 0, "B": 0, "C": 1},
    )
    assert body["not_attend"]["score"] == official_total(
        db, entry, matches_by_class={"A": 0, "B": 0, "C": 1}
    )


def test_selecting_an_institutional_event_adds_only_its_points(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)
    event = upcoming(db, "I-1", tipo="Institucional", clase=None, puntos=40)

    body = client.get(URL.format(event.id_interno), headers=headers).json()

    entry = entry_of(db, socio)
    assert body["event"]["tipo"] == "Evento institucional/amateur"
    assert body["event"]["puntos"] == 40
    base = scoring_inputs_from_snapshot(entry.inputs)
    assert body["attend"]["score"] == official_total(
        db, entry, institutional_points=base.institutional_points + 40
    )
    assert body["not_attend"] == {
        "score": f"{entry.total:.2f}",
        "difference": "0.00",
        "position": None,
    }
    assert body["position_estimate"]["reason"] == "INSTITUTIONAL_NOT_ESTIMATED"


def test_simulating_does_not_change_the_real_score(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)
    event = upcoming(db, "P-1")
    before = entry_of(db, socio)
    total, inputs = before.total, dict(before.inputs)

    for _ in range(3):
        assert (
            client.get(URL.format(event.id_interno), headers=headers).status_code == 200
        )

    db.expire_all()
    after = entry_of(db, socio)
    assert (after.total, after.inputs) == (total, inputs)


def test_an_event_of_another_club_is_not_found(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    _, headers = account()
    run(client, boca)
    foreign = upcoming(db, "P-1", club_id=RIVER_ID)

    for event_id in (foreign.id_interno, "no-existe"):
        response = client.get(URL.format(event_id), headers=headers)
        assert response.status_code == 404
        assert response.json()["detail"] == {
            "code": "EVENT_NOT_FOUND",
            "message": "No encontramos el evento.",
        }


# --- Escenario 2: un socio fuera del ranking no puede simular -------------------------------

STATUS_URL = "/member/scoring/simulator"
NOT_IN_RANKING = {
    "code": "NOT_IN_RANKING",
    "message": "Para simular necesitás un puntaje calculado. "
    "Todavía no estás en el ranking.",
}


@pytest.fixture
def outside_ranking(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    boca: dict[str, str],
    account,
    make_member: MakeMember,
):
    """Arma cada caso del escenario 2 y devuelve los headers del socio que consulta."""

    def make(case: str) -> dict[str, str]:
        publish_rules(client, boca)
        if case == "no_ranking":
            return account()[1]
        account()  # alguien del club, para que el ranking tenga población
        if case == "joined_after":
            run(client, boca)
            return account()[1]
        if case == "fees_overdue":
            socio, headers = account()
            run(client, boca)
            socio.estado_cuota = "moroso"
            db.commit()
            return headers
        assert case == "not_in_roster"
        run(client, boca)
        member = make_member(activated=True, dni="99999999", club_id=BOCA_ID)
        headers = bearer(member_token(client, outbox, member))
        outbox.clear()
        return headers

    return make


CASES = ("no_ranking", "joined_after", "fees_overdue", "not_in_roster")


@pytest.mark.parametrize("case", CASES)
def test_opening_the_simulator_outside_the_ranking_shows_the_message(
    client: TestClient, outside_ranking, case: str
) -> None:
    headers = outside_ranking(case)

    response = client.get(STATUS_URL, headers=headers)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "status": "unavailable",
        "reason": NOT_IN_RANKING["code"],
        "message": NOT_IN_RANKING["message"],
        "ranking": None,
    }


@pytest.mark.parametrize("case", CASES)
def test_simulating_an_event_outside_the_ranking_is_rejected(
    client: TestClient, db: Session, outside_ranking, case: str
) -> None:
    headers = outside_ranking(case)
    event = upcoming(db, "P-1")

    response = client.get(URL.format(event.id_interno), headers=headers)

    assert response.status_code == 409
    assert response.json()["detail"] == NOT_IN_RANKING


def test_a_ranked_socio_can_open_the_simulator(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)

    body = client.get(STATUS_URL, headers=headers).json()

    ranking = ranking_service.get_ranking_in_force(db, socio.club_id)
    assert ranking is not None and ranking.completed_at is not None
    assert body["status"] == "available"
    assert body["reason"] is None and body["message"] is None
    assert body["ranking"]["rules_version"] == 1
    assert body["ranking"]["calculation_date"] == ranking.calculation_date.isoformat()


def test_an_admin_cannot_open_the_simulator(
    client: TestClient, boca: dict[str, str]
) -> None:
    assert client.get(STATUS_URL, headers=boca).status_code == 403

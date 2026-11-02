"""HU-14: puntaje actual y posición del Socio en el ranking vigente (HU-25)."""

import re
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import RankingEntry, RankingState, Socio, User
from app.services import ranking_service
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
    adjust_rules,
    headers_for,
    make_ranking,
    make_socio,
    publish_rules,
)

URL = "/member/scoring/current"
COMPONENTS = (
    "attendance_frequency",
    "attendance_distance",
    "institutional",
    "seniority_age",
    "new_member_bonus",
    "cap_adjustment",
)


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


def run(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(RUNS, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def entry_of(db: Session, socio: Socio) -> RankingEntry:
    ranking = ranking_service.get_ranking_in_force(db, socio.club_id)
    assert ranking is not None
    return db.scalars(
        select(RankingEntry).where(
            RankingEntry.ranking_id == ranking.id,
            RankingEntry.socio_id == socio.id,
        )
    ).one()


def entries_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(RankingEntry)) or 0


def set_fees(db: Session, socio: Socio, estado: str) -> None:
    socio.estado_cuota = estado
    db.commit()


# --- Escenario 1: puntaje total en escala 0 a 100 con dos decimales -------------------------


def test_a_ranked_socio_sees_their_total_score_with_two_decimals(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)

    body = client.get(URL, headers=headers).json()

    entry = entry_of(db, socio)
    assert body["status"] == "ranked"
    assert body["reason"] is None
    assert body["label"] is None
    assert body["message"] is None
    assert re.fullmatch(r"\d{1,3}\.\d{2}", body["score"])
    assert Decimal(body["score"]) == entry.total
    assert Decimal(0) <= Decimal(body["score"]) <= Decimal(100)


def test_the_score_equals_the_sum_of_the_breakdown(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account()
    run(client, boca)

    body = client.get(URL, headers=headers).json()

    entry = entry_of(db, socio)
    assert Decimal(body["score"]) == sum(
        (getattr(entry, name) for name in COMPONENTS), Decimal(0)
    )


# --- Escenario 2: "puesto X de N socios" ----------------------------------------------------


def test_every_ranked_socio_sees_their_position_out_of_the_ranked_total(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    accounts = [account() for _ in range(3)]
    run(client, boca)

    for socio, headers in accounts:
        body = client.get(URL, headers=headers).json()
        assert body["position"] == entry_of(db, socio).position
        assert body["ranked_total"] == 3
    positions = {client.get(URL, headers=h).json()["position"] for _, h in accounts}
    assert positions == {1, 2, 3}


def test_the_ranked_total_counts_socios_without_an_account(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    _, headers = account()
    make_socio(db)
    make_socio(db)
    run(client, boca)

    assert client.get(URL, headers=headers).json()["ranked_total"] == 3


# --- Escenario 3: fecha y hora del último ranking completado y su versión de reglas ---------


def test_the_date_and_rules_version_of_the_latest_completed_ranking_are_shown(
    client: TestClient, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    _, headers = account()
    completed = run(client, boca)

    ranking = client.get(URL, headers=headers).json()["ranking"]

    assert ranking == {
        "completed_at": completed["completed_at"],
        "rules_version": 1,
    }


def test_the_rules_version_is_the_one_the_ranking_used_not_the_one_in_force(
    client: TestClient, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    _, headers = account()
    run(client, boca)
    adjust_rules(client, boca, 1, b_max="10.0")

    assert client.get(URL, headers=headers).json()["ranking"]["rules_version"] == 1


# --- Escenario 4: no está en el último ranking completado -----------------------------------


def test_a_socio_who_joined_after_the_ranking_sees_the_provisional_view(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    make_socio(db)
    completed = run(client, boca)
    stored = entries_count(db)
    _, headers = account()

    body = client.get(URL, headers=headers).json()

    assert body == {
        "status": "provisional",
        "reason": "NOT_IN_RANKING",
        "score": "0.00",
        "position": 2,
        "ranked_total": 2,
        "ranking": {
            "completed_at": completed["completed_at"],
            "rules_version": 1,
        },
        "label": ranking_service.PROVISIONAL_LABEL,
        "message": ranking_service.NOT_IN_RANKING_MESSAGE,
    }
    assert ranking_service.PROVISIONAL_LABEL == "Provisional: todavía no calculado"
    # La posición provisional es solo de pantalla: no se guarda nada.
    assert entries_count(db) == stored


def test_without_any_ranking_the_view_is_provisional_and_without_position(
    client: TestClient, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    _, headers = account()

    response = client.get(URL, headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "status": "provisional",
        "reason": "NO_RANKING",
        "score": "0.00",
        "position": None,
        "ranked_total": 0,
        "ranking": None,
        "label": ranking_service.PROVISIONAL_LABEL,
        "message": ranking_service.NO_RANKING_MESSAGE,
    }


def test_without_published_rules_the_view_is_provisional_too(
    client: TestClient, account
) -> None:
    _, headers = account()

    body = client.get(URL, headers=headers).json()

    assert body["status"] == "provisional"
    assert body["reason"] == "NO_RANKING"


def test_a_completed_ranking_without_ranked_socios_shows_no_position(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    socio, headers = account(estado_cuota="moroso")
    completed = run(client, boca)
    assert completed["population_size"] == 0
    set_fees(db, socio, "al_dia")

    body = client.get(URL, headers=headers).json()

    assert body["reason"] == "NO_RANKING"
    assert body["position"] is None
    assert body["ranked_total"] == 0
    assert body["ranking"] == {
        "completed_at": completed["completed_at"],
        "rules_version": 1,
    }


def test_a_socio_removed_from_the_roster_sees_the_provisional_view(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    _, headers = account(activo=False)
    run(client, boca)

    body = client.get(URL, headers=headers).json()

    assert body["reason"] == "NOT_IN_RANKING"
    assert body["position"] == 1
    assert body["ranked_total"] == 1


def test_an_account_without_a_roster_entry_sees_the_provisional_view(
    client: TestClient,
    outbox: Outbox,
    db: Session,
    boca: dict[str, str],
    make_member: MakeMember,
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    run(client, boca)
    headers = bearer(member_token(client, outbox, make_member(activated=True)))

    body = client.get(URL, headers=headers).json()

    assert body["reason"] == "NOT_IN_RANKING"
    assert body["position"] == 1


# --- Escenario 5: cuotas vencidas -----------------------------------------------------------


def test_an_overdue_socio_sees_the_provisional_view_with_the_explanation(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    _, headers = account(estado_cuota="moroso")
    run(client, boca)

    body = client.get(URL, headers=headers).json()

    assert body["status"] == "provisional"
    assert body["reason"] == "FEES_OVERDUE"
    assert body["score"] == "0.00"
    assert body["position"] == 1
    assert body["ranked_total"] == 1
    assert body["label"] == ranking_service.PROVISIONAL_LABEL
    message = body["message"]
    assert message == ranking_service.FEES_OVERDUE_MESSAGE
    assert "cuota al día" in message
    assert "historial" in message
    assert "regularizar tu cuota" in message


def test_a_ranked_socio_whose_fees_are_overdue_now_sees_the_overdue_view(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    socio, headers = account()
    run(client, boca)
    assert entry_of(db, socio) is not None
    set_fees(db, socio, "moroso")

    body = client.get(URL, headers=headers).json()

    assert body["reason"] == "FEES_OVERDUE"
    assert body["score"] == "0.00"
    assert body["position"] == 2
    assert body["ranked_total"] == 2


def test_a_socio_who_paid_up_after_the_ranking_waits_for_the_next_one(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    make_socio(db)
    socio, headers = account(estado_cuota="moroso")
    run(client, boca)
    set_fees(db, socio, "al_dia")

    assert client.get(URL, headers=headers).json()["reason"] == "NOT_IN_RANKING"

    run(client, boca)
    body = client.get(URL, headers=headers).json()
    assert body["status"] == "ranked"
    assert body["ranked_total"] == 2


def test_an_overdue_socio_without_any_ranking_sees_the_overdue_view(
    client: TestClient, account
) -> None:
    _, headers = account(estado_cuota="moroso")

    body = client.get(URL, headers=headers).json()

    assert body["reason"] == "FEES_OVERDUE"
    assert body["position"] is None
    assert body["ranking"] is None


# --- Escenario 6: cálculo en curso o fallido ------------------------------------------------


@pytest.mark.parametrize("state", [RankingState.RUNNING, RankingState.FAILED])
def test_a_running_or_failed_calculation_shows_the_latest_completed_ranking(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    account,
    state: RankingState,
) -> None:
    publish_rules(client, boca)
    _, headers = account()
    run(client, boca)
    before = client.get(URL, headers=headers).json()

    make_ranking(db, admin, state)

    assert client.get(URL, headers=headers).json() == before


@pytest.mark.parametrize("state", [RankingState.RUNNING, RankingState.FAILED])
def test_a_running_or_failed_first_calculation_is_not_shown(
    client: TestClient,
    db: Session,
    admin: User,
    boca: dict[str, str],
    account,
    state: RankingState,
) -> None:
    publish_rules(client, boca)
    _, headers = account()
    make_ranking(db, admin, state)

    assert client.get(URL, headers=headers).json()["reason"] == "NO_RANKING"


def test_a_new_ranking_replaces_what_the_socio_sees(
    client: TestClient, db: Session, boca: dict[str, str], account
) -> None:
    publish_rules(client, boca)
    _, headers = account()
    run(client, boca)
    adjust_rules(client, boca, 1, b_max="10.0")
    make_socio(db)

    second = run(client, boca)

    body = client.get(URL, headers=headers).json()
    assert body["ranking"] == {
        "completed_at": second["completed_at"],
        "rules_version": 2,
    }
    assert body["ranked_total"] == 2


# --- Solo lectura, autenticación y club -----------------------------------------------------


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_the_screen_is_read_only(client: TestClient, account, method: str) -> None:
    _, headers = account()

    assert getattr(client, method)(URL, headers=headers).status_code == 405


def test_the_response_is_not_cached(client: TestClient, account) -> None:
    _, headers = account()

    assert client.get(URL, headers=headers).headers["Cache-Control"] == "no-store"


def test_requires_authentication(client: TestClient) -> None:
    response = client.get(URL)

    assert response.status_code == 401


def test_an_admin_is_rejected(client: TestClient, boca: dict[str, str]) -> None:
    response = client.get(URL, headers=boca)

    assert response.status_code == 403
    assert response.json()["detail"] == "FORBIDDEN"


def test_an_account_without_club_is_rejected(
    client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    headers = bearer(
        member_token(client, outbox, make_member(activated=True, club_id=None))
    )

    response = client.get(URL, headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "MEMBER_WITHOUT_CLUB"


def test_the_club_comes_from_the_account_and_not_from_the_request(
    client: TestClient,
    outbox: Outbox,
    db: Session,
    make_admin: MakeAdmin,
    account,
) -> None:
    river = headers_for(client, outbox, make_admin(RIVER_ID))
    publish_rules(client, river)
    make_socio(db, club_id=RIVER_ID)
    run(client, river)
    _, headers = account()

    for query in ("", f"?club_id={RIVER_ID}"):
        body = client.get(
            f"{URL}{query}", headers={**headers, "X-Club-ID": str(RIVER_ID)}
        ).json()
        assert body["reason"] == "NO_RANKING"


def test_the_same_document_in_another_club_does_not_leak_its_entry(
    client: TestClient,
    outbox: Outbox,
    db: Session,
    make_admin: MakeAdmin,
    boca: dict[str, str],
    account,
) -> None:
    publish_rules(client, boca)
    socio, headers = account(estado_cuota="moroso")
    river = headers_for(client, outbox, make_admin(RIVER_ID))
    publish_rules(client, river)
    make_socio(db, club_id=RIVER_ID, dni=socio.dni)
    run(client, river)
    run(client, boca)

    body = client.get(URL, headers=headers).json()

    assert body["reason"] == "FEES_OVERDUE"
    assert body["ranked_total"] == 0

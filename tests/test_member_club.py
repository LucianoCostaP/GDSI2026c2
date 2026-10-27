"""Club del Socio (decisión 34): lo define el socio, lo hereda la cuenta al activarse y de ahí
salen los endpoints del Socio, nunca de un parámetro del pedido."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentMemberClub
from app.db import get_db
from app.models import User
from tests.conftest import (
    BOCA_ID,
    RIVER_ID,
    MakeAdmin,
    MakeMember,
    Outbox,
    admin_token,
    bearer,
    last_code,
    member_token,
)

# Endpoint mínimo que usa la dependencia: los endpoints reales del Socio (HU-13) llegan después,
# pero la regla de dónde sale el club se prueba ya, con el mismo recorrido de sesión y de roles.
probe = FastAPI()


@probe.get("/probe/club")
def club_of_member(club_id: CurrentMemberClub) -> dict[str, str]:
    return {"club_id": str(club_id)}


@pytest.fixture
def probe_client(db: Session) -> Iterator[TestClient]:
    probe.dependency_overrides[get_db] = lambda: db
    yield TestClient(probe)
    probe.dependency_overrides.clear()


def activate(client: TestClient, outbox: Outbox, member_id: str) -> None:
    sent = client.post(
        "/auth/member/activation/request", json={"identifier": member_id}
    )
    assert sent.status_code == 202
    verified = client.post(
        "/auth/member/activation/verify",
        json={"challenge": sent.json()["challenge"], "code": last_code(outbox)},
    )
    assert verified.status_code == 204


def test_activation_copies_the_club_of_the_member_to_the_account(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    river = make_member(club_id=RIVER_ID)
    boca = make_member(club_id=BOCA_ID)

    activate(client, outbox, river.member_id)
    activate(client, outbox, boca.member_id)

    clubs = {
        user.member_id: user.club_id
        for user in db.scalars(select(User).where(User.member_id.is_not(None)))
    }
    assert clubs[river.member_id] == RIVER_ID
    assert clubs[boca.member_id] == BOCA_ID


def test_activation_of_a_member_without_club_leaves_the_account_without_club(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(club_id=None)

    activate(client, outbox, member.member_id)

    user = db.scalars(select(User).where(User.member_id == member.member_id)).one()
    assert user.club_id is None


def test_the_club_comes_from_the_account_of_the_member(
    client: TestClient,
    probe_client: TestClient,
    outbox: Outbox,
    make_member: MakeMember,
) -> None:
    river = make_member(activated=True, club_id=RIVER_ID)
    headers = bearer(member_token(client, outbox, river))

    response = probe_client.get("/probe/club", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"club_id": str(RIVER_ID)}


def test_a_club_sent_in_the_request_is_ignored(
    client: TestClient,
    probe_client: TestClient,
    outbox: Outbox,
    make_member: MakeMember,
) -> None:
    boca = make_member(activated=True, club_id=BOCA_ID)
    headers = bearer(member_token(client, outbox, boca))

    response = probe_client.get(
        f"/probe/club?club_id={RIVER_ID}",
        headers={**headers, "X-Club-ID": str(RIVER_ID)},
    )

    assert response.status_code == 200
    assert response.json() == {"club_id": str(BOCA_ID)}


def test_a_member_without_club_is_rejected_and_no_club_is_guessed(
    client: TestClient,
    probe_client: TestClient,
    outbox: Outbox,
    make_member: MakeMember,
) -> None:
    member = make_member(activated=True, club_id=None)
    headers = bearer(member_token(client, outbox, member))

    response = probe_client.get("/probe/club", headers=headers)

    assert (response.status_code, response.json()["detail"]) == (
        403,
        "MEMBER_WITHOUT_CLUB",
    )


def test_an_admin_is_rejected_and_a_request_without_session_is_unauthenticated(
    client: TestClient,
    probe_client: TestClient,
    outbox: Outbox,
    make_admin: MakeAdmin,
) -> None:
    admin = make_admin(BOCA_ID)
    headers = bearer(admin_token(client, outbox, admin))

    as_admin = probe_client.get("/probe/club", headers=headers)
    anonymous = probe_client.get("/probe/club")

    assert (as_admin.status_code, as_admin.json()["detail"]) == (403, "FORBIDDEN")
    assert (anonymous.status_code, anonymous.json()["detail"]) == (
        401,
        "NOT_AUTHENTICATED",
    )


def test_each_member_has_their_own_club_even_with_the_same_session_flow(
    client: TestClient,
    probe_client: TestClient,
    outbox: Outbox,
    make_member: MakeMember,
) -> None:
    boca = make_member(activated=True, club_id=BOCA_ID)
    river = make_member(activated=True, club_id=RIVER_ID)

    clubs = []
    for member in (boca, river):
        headers = bearer(member_token(client, outbox, member))
        clubs.append(probe_client.get("/probe/club", headers=headers).json()["club_id"])

    assert clubs == [str(BOCA_ID), str(RIVER_ID)]
    assert uuid.UUID(clubs[0]) != uuid.UUID(clubs[1])

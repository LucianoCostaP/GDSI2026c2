"""El club del Admin sale de su cuenta (decisión 34): lo heredan las cuentas que invita."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_admin_club_id
from app.models import AdminAccountState, AdminInvitation, AuditLog, User
from tests.conftest import (
    BOCA_ID,
    RIVER_ID,
    MakeAdmin,
    Outbox,
    admin_token,
    bearer,
    unique,
)


def invite(client: TestClient, headers: dict[str, str], email: str):
    return client.post(
        "/admin/accounts",
        json={"name": "Nueva Admin", "email": email, "email_confirmation": email},
        headers=headers,
    )


def headers_of(client: TestClient, outbox: Outbox, user: User) -> dict[str, str]:
    headers = bearer(admin_token(client, outbox, user))
    outbox.clear()
    return headers


def expire_invitations(db: Session, user: User) -> None:
    for invitation in db.scalars(
        select(AdminInvitation).where(AdminInvitation.user_id == user.id)
    ):
        invitation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.flush()


def test_club_id_is_the_one_of_the_account(make_admin: MakeAdmin) -> None:
    assert get_current_admin_club_id(make_admin(RIVER_ID)) == RIVER_ID


def test_admin_without_club_is_rejected(make_admin: MakeAdmin) -> None:
    with pytest.raises(HTTPException) as error:
        get_current_admin_club_id(make_admin(None))

    assert (error.value.status_code, error.value.detail) == (403, "ADMIN_WITHOUT_CLUB")


def test_invited_admin_belongs_to_the_club_of_who_invites(
    client: TestClient, outbox: Outbox, db: Session, make_admin: MakeAdmin
) -> None:
    river_admin = make_admin(RIVER_ID)
    email = f"nuevo-{unique()}@example.com"

    response = invite(client, headers_of(client, outbox, river_admin), email)

    assert response.status_code == 201
    invited = db.scalars(select(User).where(User.email == email)).one()
    assert invited.club_id == RIVER_ID
    audit = db.scalars(
        select(AuditLog).where(AuditLog.entity_id == str(invited.id))
    ).one()
    assert audit.details["club_id"] == str(RIVER_ID)


def test_admin_without_club_cannot_invite(
    client: TestClient, outbox: Outbox, db: Session, make_admin: MakeAdmin
) -> None:
    email = f"nuevo-{unique()}@example.com"

    response = invite(client, headers_of(client, outbox, make_admin(None)), email)

    assert (response.status_code, response.json()["detail"]) == (
        403,
        "ADMIN_WITHOUT_CLUB",
    )
    assert db.scalar(select(User).where(User.email == email)) is None
    assert outbox == []


def test_pending_account_of_another_club_is_not_touched(
    client: TestClient, outbox: Outbox, db: Session, make_admin: MakeAdmin
) -> None:
    email = f"nuevo-{unique()}@example.com"
    boca = headers_of(client, outbox, make_admin(BOCA_ID))
    river = headers_of(client, outbox, make_admin(RIVER_ID))
    assert invite(client, boca, email).status_code == 201
    pending = db.scalars(select(User).where(User.email == email)).one()
    expire_invitations(db, pending)  # en el mismo club se podría reemplazar
    outbox.clear()

    response = invite(client, river, email)

    assert (response.status_code, response.json()["detail"]) == (
        409,
        "ACCOUNT_ALREADY_EXISTS",
    )
    db.refresh(pending)
    assert (pending.club_id, pending.name, pending.admin_state) == (
        BOCA_ID,
        "Nueva Admin",
        AdminAccountState.PENDING_ACTIVATION,
    )
    assert outbox == []


def test_expired_invitation_of_the_same_club_keeps_the_club(
    client: TestClient, outbox: Outbox, db: Session, make_admin: MakeAdmin
) -> None:
    email = f"nuevo-{unique()}@example.com"
    boca = headers_of(client, outbox, make_admin(BOCA_ID))
    assert invite(client, boca, email).status_code == 201
    pending = db.scalars(select(User).where(User.email == email)).one()
    expire_invitations(db, pending)

    response = invite(client, boca, email)

    assert response.status_code == 201
    db.refresh(pending)
    assert pending.club_id == BOCA_ID

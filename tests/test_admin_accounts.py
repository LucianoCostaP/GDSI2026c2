import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AdminAccountState, AdminInvitation, AuditLog, User
from tests.conftest import (
    MakeMember,
    Outbox,
    admin_token,
    bearer,
    member_token,
    unique,
)


@pytest.fixture
def new_email() -> str:
    return f"nuevo-{unique()}@example.com"


@pytest.fixture
def headers(client: TestClient, outbox: Outbox, admin: User) -> dict[str, str]:
    token = admin_token(client, outbox, admin)
    outbox.clear()
    return bearer(token)


def create(
    client: TestClient, headers: dict[str, str], email: str, confirmation: str = ""
) -> dict:
    response = client.post(
        "/admin/accounts",
        json={
            "name": "Nueva Admin",
            "email": email,
            "email_confirmation": confirmation or email,
        },
        headers=headers,
    )
    return {"status": response.status_code, **response.json()}


def invitation_token(outbox: Outbox) -> str:
    match = re.search(r"token=(\S+)", outbox[-1][2])
    assert match
    return match.group(1)


def accept(client: TestClient, token: str) -> dict:
    response = client.post("/admin/invitations/accept", json={"token": token})
    return {"status": response.status_code, **response.json()}


def test_create_admin_sends_invitation_and_activation_enables_login(
    client: TestClient, outbox: Outbox, headers: dict[str, str], new_email: str
) -> None:
    created = create(client, headers, new_email.upper())
    to, _, body = outbox[-1]
    accepted = accept(client, invitation_token(outbox))
    login = client.post("/auth/admin/login/request", json={"email": new_email})

    assert created["status"] == 201
    assert (created["email"], created["state"]) == (new_email, "pending_activation")
    assert to == new_email
    assert "/admin-invitation?token=" in body
    assert "48 horas" in body
    assert accepted == {"status": 200, "email_hint": "n***@example.com"}
    assert login.status_code == 202


def test_emails_must_match(
    client: TestClient, headers: dict[str, str], new_email: str
) -> None:
    created = create(client, headers, new_email, "otro@example.com")

    assert created["detail"] == "EMAILS_DO_NOT_MATCH"


def test_invalid_email(client: TestClient, headers: dict[str, str]) -> None:
    assert create(client, headers, "no-es-un-mail")["status"] == 422


def test_existing_active_or_pending_account_is_rejected(
    client: TestClient, headers: dict[str, str], admin: User, new_email: str
) -> None:
    create(client, headers, new_email)

    assert create(client, headers, admin.email)["detail"] == "ACCOUNT_ALREADY_EXISTS"
    assert create(client, headers, new_email)["detail"] == "INVITATION_PENDING"


def test_expired_invitation_can_be_created_again_and_replaces_it(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    headers: dict[str, str],
    new_email: str,
) -> None:
    create(client, headers, new_email)
    old_token = invitation_token(outbox)
    for invitation in db.scalars(select(AdminInvitation)):
        invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()

    again = create(client, headers, new_email)

    assert again["status"] == 201
    assert accept(client, old_token)["detail"] == "TOKEN_REPLACED"
    assert accept(client, invitation_token(outbox))["status"] == 200


def test_invitation_link_is_single_use_and_expires(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    headers: dict[str, str],
    new_email: str,
) -> None:
    create(client, headers, new_email)
    token = invitation_token(outbox)
    accept(client, token)

    assert accept(client, token)["detail"] == "TOKEN_USED"

    other = f"otro-{unique()}@example.com"
    create(client, headers, other)
    expiring = invitation_token(outbox)
    user = db.scalars(select(User).where(User.email == other)).one()
    invitation = db.scalars(
        select(AdminInvitation).where(AdminInvitation.user_id == user.id)
    ).one()
    invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()

    assert accept(client, expiring)["detail"] == "TOKEN_EXPIRED"
    db.refresh(user)
    assert user.admin_state == AdminAccountState.PENDING_ACTIVATION


def test_only_admins_can_create_accounts(
    client: TestClient, outbox: Outbox, make_member: MakeMember, new_email: str
) -> None:
    member = make_member(activated=True)
    member_headers = bearer(member_token(client, outbox, member))

    assert create(client, member_headers, new_email)["detail"] == "FORBIDDEN"
    assert create(client, {}, new_email)["status"] == 401


def audit_actions(db: Session, user_id: int) -> list[tuple[str, int | None]]:
    entries = db.scalars(
        select(AuditLog)
        .where(AuditLog.entity == "user", AuditLog.entity_id == str(user_id))
        .order_by(AuditLog.id)
    )
    return [(entry.action, entry.actor_user_id) for entry in entries]


def test_creation_replacement_and_activation_are_audited(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    headers: dict[str, str],
    admin: User,
    new_email: str,
) -> None:
    created = create(client, headers, new_email)
    for invitation in db.scalars(select(AdminInvitation)):
        invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    create(client, headers, new_email)
    accept(client, invitation_token(outbox))

    assert audit_actions(db, created["id"]) == [
        ("admin_account.created", admin.id),
        ("admin_account.invitation_replaced", admin.id),
        ("admin_account.activated", created["id"]),
    ]

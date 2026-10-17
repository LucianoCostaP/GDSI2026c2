from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AdminAccountState, Role, User, UserSession
from tests.conftest import MakeMember, Outbox, admin_token, bearer, last_code

# Login de admin (HU-06)


def test_admin_login_with_code(client: TestClient, outbox: Outbox, admin: User) -> None:
    sent = client.post("/auth/admin/login/request", json={"email": admin.email.lower()})
    response = client.post(
        "/auth/admin/login/verify",
        json={"challenge": sent.json()["challenge"], "code": last_code(outbox)},
    )

    assert sent.status_code == 202
    assert outbox[0][0] == admin.email
    assert response.status_code == 200
    assert response.json()["user"] == {
        "id": admin.id,
        "member_id": None,
        "name": "Admin",
        "email": admin.email,
        "role": "admin",
    }


def test_admin_login_generic_error_for_unknown_or_pending(
    client: TestClient, db: Session, outbox: Outbox
) -> None:
    pending = User(
        name="Pendiente",
        email="pendiente@example.com",
        role=Role.ADMIN,
        admin_state=AdminAccountState.PENDING_ACTIVATION,
    )
    db.add(pending)
    db.flush()

    unknown = client.post(
        "/auth/admin/login/request", json={"email": "nadie@example.com"}
    )
    not_active = client.post("/auth/admin/login/request", json={"email": pending.email})

    assert unknown.json() == not_active.json() == {"detail": "LOGIN_NOT_POSSIBLE"}
    assert outbox == []


def test_admin_door_rejects_dni(client: TestClient) -> None:
    response = client.post("/auth/admin/login/request", json={"email": "30111222"})

    assert response.status_code == 422


def test_member_account_cannot_use_admin_door(
    client: TestClient, make_member: MakeMember
) -> None:
    member = make_member(activated=True)

    response = client.post("/auth/admin/login/request", json={"email": member.email})

    assert response.json()["detail"] == "LOGIN_NOT_POSSIBLE"


def test_code_requests_are_rate_limited_per_ip(client: TestClient) -> None:
    for i in range(10):
        client.post("/auth/admin/login/request", json={"email": f"x{i}@example.com"})

    response = client.post(
        "/auth/admin/login/request", json={"email": "otro@example.com"}
    )

    assert response.status_code == 429


# Sesiones y logout (HU-11)


def test_me_returns_logged_in_user(
    client: TestClient, outbox: Outbox, admin: User
) -> None:
    headers = bearer(admin_token(client, outbox, admin))

    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 200
    assert response.json()["email"] == admin.email


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer inventado"}])
def test_me_requires_valid_session(client: TestClient, headers: dict[str, str]) -> None:
    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "NOT_AUTHENTICATED"


@pytest.mark.parametrize(
    ("created_ago", "idle_for"),
    [(timedelta(hours=1), timedelta(minutes=31)), (timedelta(hours=13), timedelta(0))],
)
def test_me_rejects_expired_session(
    client: TestClient,
    db: Session,
    outbox: Outbox,
    admin: User,
    created_ago: timedelta,
    idle_for: timedelta,
) -> None:
    headers = bearer(admin_token(client, outbox, admin))
    session = db.scalars(
        select(UserSession).where(UserSession.user_id == admin.id)
    ).one()
    now = datetime.now(UTC)
    session.created_at = now - created_ago
    session.last_seen_at = now - idle_for
    db.flush()

    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"] == "SESSION_EXPIRED"


def test_logout_revokes_session(
    client: TestClient, outbox: Outbox, admin: User
) -> None:
    headers = bearer(admin_token(client, outbox, admin))

    response = client.post("/auth/logout", headers=headers)

    assert response.status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401

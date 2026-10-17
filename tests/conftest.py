import re
import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine, get_db
from app.mailer import get_mailer
from app.main import app
from app.models import FeeStatus, Member, MemberAccountState, Role, User
from app.rate_limit import identifier_limiter, ip_limiter

Outbox = list[tuple[str, str, str]]
MakeMember = Callable[..., Member]


@pytest.fixture
def db() -> Iterator[Session]:
    # Cada test corre dentro de una transacción que se descarta al final.
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        yield session
        session.close()
        transaction.rollback()


@pytest.fixture
def outbox() -> Outbox:
    return []


@pytest.fixture
def client(db: Session, outbox: Outbox) -> Iterator[TestClient]:
    ip_limiter.reset()
    identifier_limiter.reset()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_mailer] = lambda: lambda *email: outbox.append(email)
    yield TestClient(app)
    app.dependency_overrides.clear()


def unique() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture
def make_member(db: Session) -> MakeMember:
    def make(
        *,
        activated: bool = False,
        fee_status: FeeStatus = FeeStatus.UP_TO_DATE,
        email: str | None = "",
        dni: str | None = None,
        member_id: str | None = None,
    ) -> Member:
        suffix = unique()
        member = Member(
            member_id=member_id or str(uuid.uuid4().int)[:10],
            dni=dni or str(uuid.uuid4().int)[:12],
            email=f"socio-{suffix}@example.com" if email == "" else email,
            name="Ana Socia",
            fee_status=fee_status,
            account_state=MemberAccountState.ACTIVATED
            if activated
            else MemberAccountState.NOT_ACTIVATED,
        )
        db.add(member)
        if activated:
            db.add(
                User(
                    member_id=member.member_id,
                    name=member.name,
                    email=member.email,
                    role=Role.MEMBER,
                )
            )
        db.flush()
        return member

    return make


@pytest.fixture
def admin(db: Session) -> User:
    user = User(name="Admin", email=f"Admin-{unique()}@Example.com", role=Role.ADMIN)
    db.add(user)
    db.flush()
    return user


def last_code(outbox: Outbox) -> str:
    match = re.search(r"\b(\d{6})\b", outbox[-1][2])
    assert match
    return match.group(1)


def admin_token(client: TestClient, outbox: Outbox, admin: User) -> str:
    sent = client.post("/auth/admin/login/request", json={"email": admin.email})
    assert sent.status_code == 202
    verified = client.post(
        "/auth/admin/login/verify",
        json={"challenge": sent.json()["challenge"], "code": last_code(outbox)},
    )
    assert verified.status_code == 200
    return str(verified.json()["token"])


def member_token(client: TestClient, outbox: Outbox, member: Member) -> str:
    sent = client.post(
        "/auth/member/login/request", json={"identifier": member.member_id}
    )
    assert sent.status_code == 202
    verified = client.post(
        "/auth/member/login/verify",
        json={"challenge": sent.json()["challenge"], "code": last_code(outbox)},
    )
    assert verified.status_code == 200
    return str(verified.json()["token"])


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

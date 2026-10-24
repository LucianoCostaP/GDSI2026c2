from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccessCode, AuditLog, FeeStatus, MemberAccountState, User
from tests.conftest import MakeMember, Outbox, last_code


def request_activation(client: TestClient, identifier: str, **extra: str) -> dict:
    response = client.post(
        "/auth/member/activation/request", json={"identifier": identifier, **extra}
    )
    return {"status": response.status_code, **response.json()}


def verify(client: TestClient, path: str, challenge: str, code: str) -> int:
    response = client.post(path, json={"challenge": challenge, "code": code})
    return response.status_code


def age_codes(db: Session, seconds: int) -> None:
    for access in db.scalars(select(AccessCode)):
        access.created_at -= timedelta(seconds=seconds)
    db.flush()


# Activación (HU-01)


def test_activation_by_member_id_activates_account(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member()

    sent = request_activation(client, member.member_id)
    status = verify(
        client, "/auth/member/activation/verify", sent["challenge"], last_code(outbox)
    )

    assert sent["status"] == 202
    assert sent["email_hint"] == "s***@example.com"
    assert outbox[0][0] == member.email
    assert status == 204
    db.refresh(member)
    assert member.account_state == MemberAccountState.ACTIVATED
    user = db.scalars(select(User).where(User.member_id == member.member_id)).one()
    assert (user.name, user.email, user.role) == ("Ana Socia", member.email, "member")
    audit = db.scalars(
        select(AuditLog).where(AuditLog.entity_id == member.member_id)
    ).one()
    assert (audit.action, audit.actor_user_id) == ("member_account.activated", user.id)
    assert audit.details["after"] == {"account_state": "activated"}


def test_activation_by_dni(
    client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member()

    assert request_activation(client, member.dni)["status"] == 202
    assert outbox[0][0] == member.email


def test_activation_distinct_messages(
    client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    activated = make_member(activated=True)
    overdue = make_member(fee_status=FeeStatus.OVERDUE)
    no_email = make_member(email=None)

    assert request_activation(client, "99999999999")["detail"] == "MEMBER_NOT_FOUND"
    assert (
        request_activation(client, activated.member_id)["detail"]
        == "ACCOUNT_ALREADY_ACTIVATED"
    )
    assert request_activation(client, overdue.member_id)["detail"] == "FEES_OVERDUE"
    assert request_activation(client, no_email.member_id)["detail"] == (
        "NO_EMAIL_ON_FILE"
    )
    assert outbox == []


@pytest.mark.parametrize("identifier", ["abc", "30111222x", "socio@example.com"])
def test_activation_rejects_malformed_identifier_before_lookup(
    client: TestClient, identifier: str
) -> None:
    response = request_activation(client, identifier)

    assert (response["status"], response["detail"]) == (422, "INVALID_IDENTIFIER")


def test_activation_accepts_dni_with_dots(
    client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(dni="30999888")

    assert request_activation(client, "30.999.888")["status"] == 202
    assert outbox[0][0] == member.email


def test_ambiguous_identifier_asks_for_type(
    client: TestClient, make_member: MakeMember
) -> None:
    by_dni = make_member(dni="99887766")
    make_member(member_id="99887766")

    ambiguous = request_activation(client, "99887766")
    chosen = request_activation(client, "99887766", identifier_type="dni")

    assert ambiguous["detail"] == "IDENTIFIER_TYPE_REQUIRED"
    assert chosen["status"] == 202
    assert by_dni.email
    assert chosen["email_hint"] == f"s***@{by_dni.email.split('@')[1]}"


# Reglas del código


def test_wrong_code_five_times_locks_identifier(
    client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member()
    challenge = request_activation(client, member.member_id)["challenge"]
    wrong = "000000" if last_code(outbox) != "000000" else "111111"

    statuses = [
        client.post(
            "/auth/member/activation/verify",
            json={"challenge": challenge, "code": wrong},
        ).json()["detail"]
        for _ in range(5)
    ]
    after_lock = client.post(
        "/auth/member/activation/verify",
        json={"challenge": challenge, "code": last_code(outbox)},
    )
    new_request = request_activation(client, member.member_id)

    assert statuses == ["INVALID_CODE"] * 4 + ["TOO_MANY_FAILED_ATTEMPTS"]
    assert after_lock.json()["detail"] == "TOO_MANY_FAILED_ATTEMPTS"
    assert new_request["detail"] == "IDENTIFIER_LOCKED"


def test_expired_code_is_rejected_like_a_wrong_one(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member()
    challenge = request_activation(client, member.member_id)["challenge"]
    access = db.scalars(
        select(AccessCode).where(AccessCode.member_id == member.member_id)
    ).one()
    access.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()

    response = client.post(
        "/auth/member/activation/verify",
        json={"challenge": challenge, "code": last_code(outbox)},
    )

    assert response.json()["detail"] == "INVALID_CODE"


def test_resend_waits_and_new_code_replaces_previous(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member()
    first = request_activation(client, member.member_id)
    first_code = last_code(outbox)

    too_soon = request_activation(client, member.member_id)
    age_codes(db, 61)
    second = request_activation(client, member.member_id)

    assert too_soon["detail"] == "RESEND_COOLDOWN"
    path = "/auth/member/activation/verify"
    assert verify(client, path, first["challenge"], first_code) == 400
    assert verify(client, path, second["challenge"], last_code(outbox)) == 204


def test_requests_are_limited_per_identifier(client: TestClient) -> None:
    for _ in range(5):
        request_activation(client, "99999999999")

    assert request_activation(client, "99999999999")["status"] == 429


# Login de socio (HU-05)


def login_request(client: TestClient, identifier: str) -> dict:
    response = client.post(
        "/auth/member/login/request", json={"identifier": identifier}
    )
    return {"status": response.status_code, **response.json()}


def test_login_with_dni_member_id_or_email(
    client: TestClient, db: Session, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    assert member.email

    for identifier in (member.dni, member.member_id, member.email.upper()):
        age_codes(db, 61)
        sent = login_request(client, identifier)
        response = client.post(
            "/auth/member/login/verify",
            json={"challenge": sent["challenge"], "code": last_code(outbox)},
        )
        assert response.status_code == 200
        assert response.json()["user"]["member_id"] == member.member_id
        assert response.json()["user"]["role"] == "member"


def test_login_messages(client: TestClient, make_member: MakeMember) -> None:
    not_activated = make_member()

    assert login_request(client, "99999999999")["detail"] == "LOGIN_NOT_POSSIBLE"
    assert login_request(client, not_activated.member_id)["detail"] == (
        "ACCOUNT_NOT_ACTIVATED"
    )


def test_login_with_shared_email_asks_for_dni(
    client: TestClient, make_member: MakeMember
) -> None:
    make_member(activated=True, email="familia@example.com")
    make_member(activated=True, email="familia@example.com")

    assert login_request(client, "familia@example.com")["detail"] == "EMAIL_SHARED"


def test_overdue_fees_do_not_block_login(
    client: TestClient, make_member: MakeMember
) -> None:
    member = make_member(activated=True, fee_status=FeeStatus.OVERDUE)

    assert login_request(client, member.member_id)["status"] == 202


def test_member_code_does_not_work_at_admin_door(
    client: TestClient, outbox: Outbox, make_member: MakeMember
) -> None:
    member = make_member(activated=True)
    sent = login_request(client, member.member_id)

    status = verify(
        client, "/auth/admin/login/verify", sent["challenge"], last_code(outbox)
    )

    assert status == 400


def test_login_rejects_malformed_identifier(client: TestClient) -> None:
    response = login_request(client, "no es un dni")

    assert (response["status"], response["detail"]) == (422, "INVALID_IDENTIFIER")

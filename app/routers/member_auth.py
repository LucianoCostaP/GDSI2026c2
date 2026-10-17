"""Puerta de socios: activación de la cuenta (HU-01) e inicio de sesión (HU-05), por código."""

import enum
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..access_codes import issue_code, verify_code
from ..audit import record
from ..auth import create_session
from ..db import get_db
from ..mailer import SendEmail, get_mailer, mask_email, send_code
from ..models import CodePurpose, FeeStatus, Member, MemberAccountState, Role, User
from ..rate_limit import check_key, identifier_limiter, ip_limiter, limit_by_ip
from ..schemas import CodeSent, CodeVerification, LoginResponse, UserOut

router = APIRouter(prefix="/auth/member", tags=["member auth"])

Db = Annotated[Session, Depends(get_db)]
Mailer = Annotated[SendEmail, Depends(get_mailer)]
LimitByIp = Depends(limit_by_ip(ip_limiter))


class IdentifierType(enum.StrEnum):
    DNI = "dni"
    MEMBER_ID = "member_id"
    EMAIL = "email"


class IdentifierRequest(BaseModel):
    identifier: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=320)
    ]
    # Solo hace falta cuando el identificador coincide con socios distintos según el tipo.
    identifier_type: IdentifierType | None = None


NUMBER = re.compile(r"\d{1,16}", re.ASCII)
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def parse_identifier(
    raw: str, identifier_type: IdentifierType | None, allowed: set[IdentifierType]
) -> tuple[str, set[IdentifierType]]:
    """Valida el formato antes de buscar (HU-01). DNI y número de socio son numéricos y se
    aceptan con puntos o espacios ("30.111.222"). Devuelve el valor normalizado y los tipos
    con los que puede coincidir."""
    invalid = HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "INVALID_IDENTIFIER")
    if identifier_type is not None and identifier_type not in allowed:
        raise invalid
    candidates = {identifier_type} if identifier_type else allowed

    if IdentifierType.EMAIL in candidates and EMAIL.fullmatch(raw):
        return raw, {IdentifierType.EMAIL}
    number = re.sub(r"[.\s]", "", raw)
    numeric = candidates - {IdentifierType.EMAIL}
    if numeric and NUMBER.fullmatch(number):
        return number, numeric
    raise invalid


def find_member(
    db: Session,
    raw_identifier: str,
    identifier_type: IdentifierType | None,
    allowed: set[IdentifierType],
) -> Member | None:
    identifier, types = parse_identifier(raw_identifier, identifier_type, allowed)
    criteria = {
        IdentifierType.DNI: Member.dni == identifier,
        IdentifierType.MEMBER_ID: Member.member_id == identifier,
        IdentifierType.EMAIL: func.lower(Member.email) == identifier.lower(),
    }

    matches: dict[IdentifierType, list[Member]] = {}
    for kind in types:
        found = list(db.scalars(select(Member).where(criteria[kind])))
        if found:
            matches[kind] = found

    if len(matches.get(IdentifierType.EMAIL, [])) > 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "EMAIL_SHARED")
    members = {m.member_id: m for found in matches.values() for m in found}
    if len(members) > 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "IDENTIFIER_TYPE_REQUIRED")
    return next(iter(members.values()), None)


def require_email(member: Member) -> str:
    if member.email is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "NO_EMAIL_ON_FILE")
    return member.email


@router.post(
    "/activation/request",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[LimitByIp],
)
def request_activation(body: IdentifierRequest, db: Db, send: Mailer) -> CodeSent:
    check_key(identifier_limiter, f"member:{body.identifier.lower()}")
    member = find_member(
        db,
        body.identifier,
        body.identifier_type,
        {IdentifierType.DNI, IdentifierType.MEMBER_ID},
    )
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MEMBER_NOT_FOUND")
    if member.account_state == MemberAccountState.ACTIVATED:
        raise HTTPException(status.HTTP_409_CONFLICT, "ACCOUNT_ALREADY_ACTIVATED")
    if member.fee_status == FeeStatus.OVERDUE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "FEES_OVERDUE")
    email = require_email(member)

    challenge, code = issue_code(db, CodePurpose.ACTIVATION, member_id=member.member_id)
    send_code(send, email, "Tu código para activar tu cuenta de Pasión de 10", code)
    db.commit()
    return CodeSent(challenge=challenge, email_hint=mask_email(email))


@router.post("/activation/verify", status_code=status.HTTP_204_NO_CONTENT)
def verify_activation(body: CodeVerification, db: Db) -> None:
    access = verify_code(db, CodePurpose.ACTIVATION, body.challenge, body.code)
    member = db.get_one(Member, access.member_id, with_for_update=True)
    if member.account_state == MemberAccountState.ACTIVATED:
        raise HTTPException(status.HTTP_409_CONFLICT, "ACCOUNT_ALREADY_ACTIVATED")

    member.account_state = MemberAccountState.ACTIVATED
    user = User(
        member_id=member.member_id,
        name=member.name or member.member_id,
        email=require_email(member),
        role=Role.MEMBER,
    )
    db.add(user)
    db.flush()
    record(
        db,
        "member_account.activated",
        actor_id=user.id,
        entity="member",
        entity_id=member.member_id,
        email=user.email,
        before={"account_state": MemberAccountState.NOT_ACTIVATED},
        after={"account_state": MemberAccountState.ACTIVATED},
    )
    db.commit()


@router.post(
    "/login/request", status_code=status.HTTP_202_ACCEPTED, dependencies=[LimitByIp]
)
def request_login(body: IdentifierRequest, db: Db, send: Mailer) -> CodeSent:
    check_key(identifier_limiter, f"member:{body.identifier.lower()}")
    member = find_member(db, body.identifier, body.identifier_type, set(IdentifierType))
    if member is None:
        # Mensaje genérico: no revela si el identificador existe (HU-05).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "LOGIN_NOT_POSSIBLE")
    if member.account_state != MemberAccountState.ACTIVATED:
        raise HTTPException(status.HTTP_409_CONFLICT, "ACCOUNT_NOT_ACTIVATED")
    email = require_email(member)

    challenge, code = issue_code(db, CodePurpose.LOGIN, member_id=member.member_id)
    send_code(send, email, "Tu código para entrar a Pasión de 10", code)
    db.commit()
    return CodeSent(challenge=challenge, email_hint=mask_email(email))


@router.post("/login/verify")
def verify_login(body: CodeVerification, db: Db) -> LoginResponse:
    access = verify_code(db, CodePurpose.LOGIN, body.challenge, body.code)
    if access.member_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "INVALID_CODE")
    user = db.scalars(select(User).where(User.member_id == access.member_id)).one()
    token = create_session(db, user)
    db.commit()
    return LoginResponse(token=token, user=UserOut.from_user(user))

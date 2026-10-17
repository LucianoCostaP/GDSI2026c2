"""Códigos de 6 dígitos por mail para activar la cuenta de socio y para iniciar sesión.

Reglas (cross-cutting sección 3): vencen a los 10 minutos, sirven una vez, admiten 5 intentos,
el reenvío espera 60 segundos y un código nuevo invalida el anterior. Al agotar los intentos,
el destinatario queda bloqueado 15 minutos.
"""

import math
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, select, update
from sqlalchemy.orm import Session

from .config import settings
from .models import AccessCode, CodePurpose
from .security import generate_code, generate_token, hash_token, same_hash


def _recipient(member_id: str | None, user_id: int | None) -> ColumnElement[bool]:
    if member_id is not None:
        return AccessCode.member_id == member_id
    return AccessCode.user_id == user_id


def _code_hash(challenge: str, code: str) -> str:
    return hash_token(f"{challenge}:{code}")


def _wait(seconds: float, code: str) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        code,
        headers={"Retry-After": str(max(1, math.ceil(seconds)))},
    )


def issue_code(
    db: Session,
    purpose: CodePurpose,
    *,
    member_id: str | None = None,
    user_id: int | None = None,
) -> tuple[str, str]:
    """Crea un código para el destinatario y devuelve (challenge, código)."""
    now = datetime.now(UTC)
    recipient = _recipient(member_id, user_id)

    lock_start = now - timedelta(minutes=settings.identifier_lock_minutes)
    locked_at = db.scalar(
        select(AccessCode.exhausted_at)
        .where(recipient, AccessCode.exhausted_at > lock_start)
        .order_by(AccessCode.exhausted_at.desc())
        .limit(1)
    )
    if locked_at is not None:
        unlock_at = locked_at + timedelta(minutes=settings.identifier_lock_minutes)
        raise _wait((unlock_at - now).total_seconds(), "IDENTIFIER_LOCKED")

    last_sent = db.scalar(
        select(AccessCode.created_at)
        .where(recipient, AccessCode.purpose == purpose, AccessCode.used_at.is_(None))
        .order_by(AccessCode.created_at.desc())
        .limit(1)
    )
    cooldown = timedelta(seconds=settings.access_code_resend_seconds)
    if last_sent is not None and now < last_sent + cooldown:
        raise _wait((last_sent + cooldown - now).total_seconds(), "RESEND_COOLDOWN")

    db.execute(
        update(AccessCode)
        .where(
            recipient,
            AccessCode.purpose == purpose,
            AccessCode.used_at.is_(None),
            AccessCode.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    challenge, code = generate_token(), generate_code()
    db.add(
        AccessCode(
            purpose=purpose,
            member_id=member_id,
            user_id=user_id,
            challenge_hash=hash_token(challenge),
            code_hash=_code_hash(challenge, code),
            expires_at=now + timedelta(minutes=settings.access_code_expiry_minutes),
        )
    )
    db.flush()
    return challenge, code


def verify_code(
    db: Session, purpose: CodePurpose, challenge: str, code: str
) -> AccessCode:
    """Marca el código como usado. Un código vencido se rechaza igual que uno incorrecto."""
    access = db.scalar(
        select(AccessCode)
        .where(
            AccessCode.challenge_hash == hash_token(challenge),
            AccessCode.purpose == purpose,
        )
        .with_for_update()
    )
    invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "INVALID_CODE")
    if access is None:
        raise invalid
    if access.exhausted_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "TOO_MANY_FAILED_ATTEMPTS")

    now = datetime.now(UTC)
    usable = (
        access.used_at is None and access.revoked_at is None and now < access.expires_at
    )
    if usable and same_hash(access.code_hash, _code_hash(challenge, code)):
        access.used_at = now
        return access

    if usable:
        access.attempts += 1
        if access.attempts >= settings.access_code_max_attempts:
            access.exhausted_at = now
        db.commit()
        if access.exhausted_at is not None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "TOO_MANY_FAILED_ATTEMPTS")
    raise invalid

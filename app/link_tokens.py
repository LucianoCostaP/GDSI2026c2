from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, select, update
from sqlalchemy.orm import Session

from .models import LinkToken
from .security import generate_token, hash_token


def issue_link_token[T: LinkToken](
    db: Session, model: type[T], recipient: ColumnElement[bool], **fields: Any
) -> str:
    """Invalida los links pendientes del mismo destinatario y crea uno nuevo."""
    db.execute(
        update(model)
        .where(recipient, model.used_at.is_(None), model.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    token = generate_token()
    link = model(**fields)
    link.token_hash = hash_token(token)
    db.add(link)
    db.flush()
    return token


def load_link_token[T: LinkToken](
    db: Session, model: type[T], token: str, *, for_update: bool = False
) -> T:
    query = select(model).where(model.token_hash == hash_token(token))
    if for_update:
        query = query.with_for_update()
    link = db.scalar(query)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "INVALID_TOKEN")
    if link.used_at is not None:
        raise HTTPException(status.HTTP_410_GONE, "TOKEN_USED")
    if link.revoked_at is not None:
        raise HTTPException(status.HTTP_410_GONE, "TOKEN_REPLACED")
    if link.expires_at is not None and link.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, "TOKEN_EXPIRED")
    return link

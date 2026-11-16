"""Bandeja de notificaciones del Socio (HU-20).

Lee solo las notificaciones de la cuenta de la sesión y de su club (decisión 34). Nunca lee los
campos de correo que agrega HU-19 (notificaciones §10).
"""

import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, func, select, update
from sqlalchemy.orm import Session

from ..core.date_utils import asegurar_utc
from ..models import Notification, NotificationState, User
from ..models.auth import utcnow
from ..schemas.notifications import NotificationListOut, NotificationOut, ReadAllOut
from .formula_service import error

NOT_FOUND_MESSAGE = "No encontramos esa notificación."


def _out(notification: Notification) -> NotificationOut:
    return NotificationOut(
        id=notification.id,
        type=notification.type,
        title=notification.title,
        message=notification.message,
        created_at=asegurar_utc(notification.created_at),
        state=notification.state.value,
        read_at=asegurar_utc(notification.read_at) if notification.read_at else None,
        reference=notification.reference,
    )


def list_notifications(
    db: Session, member: User, club_id: uuid.UUID, *, limit: int, offset: int
) -> NotificationListOut:
    """Una página de las notificaciones del Socio, la más reciente primero; en un empate de
    fecha, la creada después (id mayor) primero (escenario 1). El orden es total, así que las
    páginas no se pisan ni dejan huecos (escenario 6)."""
    own = (Notification.user_id == member.id, Notification.club_id == club_id)
    rows = db.scalars(
        select(Notification)
        .where(*own)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Notification).where(*own)) or 0
    return NotificationListOut(
        items=[_out(row) for row in rows],
        total=total,
        unread_count=_unread_count(db, own),
        limit=limit,
        offset=offset,
    )


def _unread_count(db: Session, own: tuple[ColumnElement[bool], ...]) -> int:
    """Las no leídas del Socio (escenario 3); usa el índice por cuenta y estado."""
    return (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(*own, Notification.state == NotificationState.UNREAD)
        )
        or 0
    )


def mark_as_read(
    db: Session,
    member: User,
    club_id: uuid.UUID,
    notification_id: int,
    *,
    now: datetime | None = None,
) -> NotificationOut:
    """Marca como leída una notificación del Socio y la devuelve (US2 escenario 1).

    No mira el evento ni el ranking de la referencia: si el destino ya no existe, la
    notificación igual queda leída y el front muestra el aviso (US2 escenario 2). Si ya estaba
    leída conserva su primera hora de lectura (FR-009). Otra cuenta, otro club o un id
    inexistente responden igual: 404 `NOTIFICATION_NOT_FOUND`.
    """
    notification = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == member.id,
            Notification.club_id == club_id,
        )
    )
    if notification is None:
        raise error(404, "NOTIFICATION_NOT_FOUND", NOT_FOUND_MESSAGE)
    if notification.state is NotificationState.UNREAD:
        notification.state = NotificationState.READ
        notification.read_at = now or utcnow()
        db.commit()
    return _out(notification)


def mark_all_as_read(
    db: Session, member: User, club_id: uuid.UUID, *, now: datetime | None = None
) -> ReadAllOut:
    """Marca como leídas todas las no leídas del Socio, no solo las de la página cargada
    (US2 escenario 4). Las que ya estaban leídas conservan su `read_at` (FR-009)."""
    # Un UPDATE devuelve un CursorResult, que es el que tiene `rowcount`.
    result = cast(
        CursorResult[Any],
        db.execute(
            update(Notification)
            .where(
                Notification.user_id == member.id,
                Notification.club_id == club_id,
                Notification.state == NotificationState.UNREAD,
            )
            .values(state=NotificationState.READ, read_at=now or utcnow())
        ),
    )
    db.commit()
    return ReadAllOut(marked=result.rowcount, unread_count=0)

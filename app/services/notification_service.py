"""Bandeja de notificaciones del Socio (HU-20).

Lee solo las notificaciones de la cuenta de la sesión y de su club (decisión 34). Nunca lee los
campos de correo que agrega HU-19 (notificaciones §10).
"""

import uuid

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from ..core.date_utils import asegurar_utc
from ..models import Notification, NotificationState, User
from ..schemas.notifications import NotificationListOut, NotificationOut


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

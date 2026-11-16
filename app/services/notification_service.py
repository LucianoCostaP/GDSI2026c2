"""Bandeja de notificaciones del Socio (HU-20).

Lee solo las notificaciones de la cuenta de la sesión y de su club (decisión 34). Nunca lee los
campos de correo que agrega HU-19 (notificaciones §10).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.date_utils import asegurar_utc
from ..models import Notification, User
from ..schemas.notifications import NotificationListOut, NotificationOut


def _out(notification: Notification) -> NotificationOut:
    return NotificationOut(
        id=notification.id,
        type=notification.type,
        title=notification.title,
        message=notification.message,
        created_at=asegurar_utc(notification.created_at),
        reference=notification.reference,
    )


def list_notifications(
    db: Session, member: User, club_id: uuid.UUID
) -> NotificationListOut:
    """Todas las notificaciones del Socio, la más reciente primero; en un empate de fecha, la
    creada después (id mayor) primero (escenario 1)."""
    rows = db.scalars(
        select(Notification)
        .where(Notification.user_id == member.id, Notification.club_id == club_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    ).all()
    return NotificationListOut(items=[_out(row) for row in rows], total=len(rows))

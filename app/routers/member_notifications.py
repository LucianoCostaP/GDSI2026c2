"""Bandeja de notificaciones del Socio (HU-20).

El club y la cuenta salen siempre de la sesión (decisión 34): estos endpoints no leen
`club_id` ni `X-Club-ID`, aunque lleguen. Contrato: `docs/contrato-api-notificaciones.md`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..auth import CurrentMember, CurrentMemberClub
from ..db import get_db
from ..schemas.notifications import NotificationListOut, NotificationOut, ReadAllOut
from ..services import notification_service

router = APIRouter(prefix="/member/notifications", tags=["member notifications"])

Db = Annotated[Session, Depends(get_db)]


@router.get("", response_model=NotificationListOut)
def list_notifications(
    member: CurrentMember,
    club_id: CurrentMemberClub,
    db: Db,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NotificationListOut:
    response.headers["Cache-Control"] = "no-store"
    return notification_service.list_notifications(
        db, member, club_id, limit=limit, offset=offset
    )


@router.post("/read-all", response_model=ReadAllOut)
def mark_all_as_read(
    member: CurrentMember, club_id: CurrentMemberClub, db: Db
) -> ReadAllOut:
    return notification_service.mark_all_as_read(db, member, club_id)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_as_read(
    notification_id: int, member: CurrentMember, club_id: CurrentMemberClub, db: Db
) -> NotificationOut:
    return notification_service.mark_as_read(db, member, club_id, notification_id)

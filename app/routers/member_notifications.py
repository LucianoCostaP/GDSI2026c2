"""Bandeja de notificaciones del Socio (HU-20).

El club y la cuenta salen siempre de la sesión (decisión 34): estos endpoints no leen
`club_id` ni `X-Club-ID`, aunque lleguen. Contrato: `docs/contrato-api-notificaciones.md`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..auth import CurrentMember, CurrentMemberClub
from ..db import get_db
from ..schemas.notifications import NotificationListOut
from ..services import notification_service

router = APIRouter(prefix="/member/notifications", tags=["member notifications"])

Db = Annotated[Session, Depends(get_db)]


@router.get("", response_model=NotificationListOut)
def list_notifications(
    member: CurrentMember, club_id: CurrentMemberClub, db: Db, response: Response
) -> NotificationListOut:
    response.headers["Cache-Control"] = "no-store"
    return notification_service.list_notifications(db, member, club_id)

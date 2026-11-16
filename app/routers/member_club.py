"""Contacto del club para el manual del Socio: a quién escribirle si algo no funciona.

El club sale de la cuenta del Socio (decisión 34), nunca de un parámetro del pedido.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import CurrentMember, CurrentMemberClub
from ..db import get_db
from ..models import AdminAccountState, Role, User
from ..models.domain import Club

router = APIRouter(prefix="/member/club", tags=["member club"])

Db = Annotated[Session, Depends(get_db)]


class AdminContact(BaseModel):
    name: str
    email: str


class ClubContact(BaseModel):
    club: str
    admin: AdminContact | None


@router.get("/contact")
def club_contact(
    _: CurrentMember, club_id: CurrentMemberClub, db: Db, response: Response
) -> ClubContact:
    response.headers["Cache-Control"] = "no-store"
    club = db.get_one(Club, club_id)
    # El más antiguo, para que el Socio vea siempre el mismo contacto.
    admin = db.scalars(
        select(User)
        .where(
            User.club_id == club_id,
            User.role == Role.ADMIN,
            User.admin_state == AdminAccountState.ACTIVE,
        )
        .order_by(User.created_at, User.id)
        .limit(1)
    ).first()
    return ClubContact(
        club=club.nombre,
        admin=AdminContact(name=admin.name, email=admin.email) if admin else None,
    )

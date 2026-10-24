"""Cuentas de admin: un admin crea otra (HU-07) y el invitado la activa con el link (HU-08)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record
from ..auth import CurrentAdmin
from ..config import settings
from ..db import get_db
from ..link_tokens import issue_link_token, load_link_token
from ..mailer import SendEmail, get_mailer, mask_email
from ..models import AdminAccountState, AdminInvitation, Role, User
from ..schemas import Name

router = APIRouter(tags=["admin accounts"])

Db = Annotated[Session, Depends(get_db)]
Mailer = Annotated[SendEmail, Depends(get_mailer)]


class CreateAdminRequest(BaseModel):
    name: Name
    email: EmailStr
    # El email se escribe dos veces: quien reciba el link activa la cuenta (HU-07).
    email_confirmation: EmailStr


class AdminAccountOut(BaseModel):
    id: int
    name: str
    email: str
    state: AdminAccountState


class AcceptInvitationRequest(BaseModel):
    token: str


class InvitationAccepted(BaseModel):
    email_hint: str


def has_valid_invitation(db: Session, user: User) -> bool:
    query = select(AdminInvitation.id).where(
        AdminInvitation.user_id == user.id,
        AdminInvitation.used_at.is_(None),
        AdminInvitation.revoked_at.is_(None),
        AdminInvitation.expires_at > datetime.now(UTC),
    )
    return db.scalar(query) is not None


@router.post("/admin/accounts", status_code=status.HTTP_201_CREATED)
def create_admin(
    body: CreateAdminRequest, admin: CurrentAdmin, db: Db, send: Mailer
) -> AdminAccountOut:
    email = body.email.lower()
    if email != body.email_confirmation.lower():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "EMAILS_DO_NOT_MATCH"
        )

    user = db.scalar(
        select(User)
        .where(User.role == Role.ADMIN, func.lower(User.email) == email)
        .with_for_update()
    )
    if user is not None and user.admin_state == AdminAccountState.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, "ACCOUNT_ALREADY_EXISTS")
    if user is not None and has_valid_invitation(db, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "INVITATION_PENDING")

    # Una cuenta pendiente con la invitación vencida se trata como nueva (HU-07, escenario 4).
    replaced = user is not None
    if user is None:
        user = User(
            email=email,
            role=Role.ADMIN,
            admin_state=AdminAccountState.PENDING_ACTIVATION,
            name=body.name,
        )
        db.add(user)
        db.flush()
    previous_name, user.name = user.name, body.name

    token = issue_link_token(
        db,
        AdminInvitation,
        AdminInvitation.user_id == user.id,
        user_id=user.id,
        invited_by_id=admin.id,
        expires_at=datetime.now(UTC)
        + timedelta(hours=settings.admin_invitation_expiry_hours),
    )
    # Quien crea la cuenta es quien invita: es una sola acción (HU-07, FR-008).
    record(
        db,
        "admin_account.invitation_replaced" if replaced else "admin_account.created",
        actor_id=admin.id,
        entity="user",
        entity_id=user.id,
        email=email,
        **(
            {"before": {"name": previous_name}, "after": {"name": user.name}}
            if replaced
            else {"name": user.name}
        ),
    )
    link = f"{settings.front_origin}/admin-invitation?token={token}"
    send(
        email,
        "Te invitaron a administrar Pasión de 10",
        f"Hola {body.name},\n\n{admin.name} te creó una cuenta de administrador "
        "en Pasión de 10.\n"
        f"Para activarla entrá a este link:\n{link}\n\n"
        f"El link vence en {settings.admin_invitation_expiry_hours} horas y sirve una "
        "sola vez. Si no esperabas esta invitación, ignorá este mail.",
    )
    db.commit()
    return AdminAccountOut(
        id=user.id, name=user.name, email=user.email, state=user.admin_state
    )


@router.post("/admin/invitations/accept")
def accept_invitation(body: AcceptInvitationRequest, db: Db) -> InvitationAccepted:
    invitation = load_link_token(db, AdminInvitation, body.token, for_update=True)
    user = db.get_one(User, invitation.user_id, with_for_update=True)
    if user.admin_state == AdminAccountState.ACTIVE:
        raise HTTPException(status.HTTP_410_GONE, "TOKEN_USED")

    user.admin_state = AdminAccountState.ACTIVE
    invitation.used_at = datetime.now(UTC)
    # Quien activa es el propio invitado: el link prueba que controla ese email (HU-08).
    record(
        db,
        "admin_account.activated",
        actor_id=user.id,
        entity="user",
        entity_id=user.id,
        email=user.email,
        invited_by_id=invitation.invited_by_id,
        before={"admin_state": AdminAccountState.PENDING_ACTIVATION},
        after={"admin_state": AdminAccountState.ACTIVE},
    )
    db.commit()
    return InvitationAccepted(email_hint=mask_email(user.email))

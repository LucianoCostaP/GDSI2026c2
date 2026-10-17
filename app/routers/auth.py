from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..access_codes import issue_code, verify_code
from ..auth import CurrentSession, CurrentUser, create_session
from ..db import get_db
from ..mailer import SendEmail, get_mailer, mask_email, send_code
from ..models import AdminAccountState, CodePurpose, Role, User
from ..rate_limit import check_key, identifier_limiter, ip_limiter, limit_by_ip
from ..schemas import CodeSent, CodeVerification, LoginResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

Db = Annotated[Session, Depends(get_db)]
Mailer = Annotated[SendEmail, Depends(get_mailer)]


class AdminLoginRequest(BaseModel):
    # Solo email: un DNI o número de socio se rechaza como email inválido (HU-06).
    email: EmailStr


@router.post(
    "/admin/login/request",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(limit_by_ip(ip_limiter))],
)
def request_admin_login(body: AdminLoginRequest, db: Db, send: Mailer) -> CodeSent:
    email = body.email.lower()
    check_key(identifier_limiter, f"admin:{email}")
    user = db.scalar(
        select(User).where(User.role == Role.ADMIN, func.lower(User.email) == email)
    )
    if user is None or user.admin_state != AdminAccountState.ACTIVE:
        # Mismo mensaje para un email desconocido o una cuenta pendiente (HU-06).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "LOGIN_NOT_POSSIBLE")

    challenge, code = issue_code(db, CodePurpose.LOGIN, user_id=user.id)
    send_code(send, user.email, "Tu código para entrar a Pasión de 10", code)
    db.commit()
    return CodeSent(challenge=challenge, email_hint=mask_email(user.email))


@router.post("/admin/login/verify")
def verify_admin_login(body: CodeVerification, db: Db) -> LoginResponse:
    access = verify_code(db, CodePurpose.LOGIN, body.challenge, body.code)
    if access.user_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "INVALID_CODE")
    user = db.get_one(User, access.user_id)
    token = create_session(db, user)
    db.commit()
    return LoginResponse(token=token, user=UserOut.from_user(user))


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.from_user(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session: CurrentSession, db: Db) -> None:
    session.revoked_at = datetime.now(UTC)
    db.commit()

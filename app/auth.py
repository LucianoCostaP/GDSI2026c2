import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .core.date_utils import asegurar_utc
from .db import get_db
from .models import Role, User, UserSession
from .security import generate_token, hash_token

_bearer = HTTPBearer(auto_error=False)


def unauthorized(code: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, code, headers={"WWW-Authenticate": "Bearer"}
    )


def create_session(db: Session, user: User) -> str:
    token = generate_token()
    db.add(UserSession(token_hash=hash_token(token), user_id=user.id))
    return token


def is_expired(session: UserSession, now: datetime) -> bool:
    last_seen = asegurar_utc(session.last_seen_at)
    created = asegurar_utc(session.created_at)
    idle_limit = last_seen + timedelta(minutes=settings.session_idle_minutes)
    absolute_limit = created + timedelta(hours=settings.session_absolute_hours)
    return now >= idle_limit or now >= absolute_limit


def get_current_session(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> UserSession:
    if credentials is None:
        raise unauthorized("NOT_AUTHENTICATED")
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(credentials.credentials)
        )
    )
    now = datetime.now(UTC)
    if session is None or session.revoked_at is not None:
        raise unauthorized("NOT_AUTHENTICATED")
    if is_expired(session, now):
        raise unauthorized("SESSION_EXPIRED")

    session.last_seen_at = now
    db.commit()
    return session


CurrentSession = Annotated[UserSession, Depends(get_current_session)]


def get_current_user(
    session: CurrentSession, db: Annotated[Session, Depends(get_db)]
) -> User:
    return db.get_one(User, session.user_id)


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_admin(user: CurrentUser) -> User:
    if user.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "FORBIDDEN")
    return user


CurrentAdmin = Annotated[User, Depends(get_current_admin)]


def get_current_admin_club_id(admin: CurrentAdmin) -> uuid.UUID:
    """Club del Admin autenticado. Es la única fuente del club en los endpoints del Admin:
    estos no leen `club_id` ni `X-Club-ID`, aunque lleguen (decisión 34)."""
    if admin.club_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ADMIN_WITHOUT_CLUB")
    return admin.club_id


CurrentAdminClub = Annotated[uuid.UUID, Depends(get_current_admin_club_id)]


def get_current_member(user: CurrentUser) -> User:
    if user.role != Role.MEMBER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "FORBIDDEN")
    return user


CurrentMember = Annotated[User, Depends(get_current_member)]

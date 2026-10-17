from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
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
    idle_limit = session.last_seen_at + timedelta(minutes=settings.session_idle_minutes)
    absolute_limit = session.created_at + timedelta(
        hours=settings.session_absolute_hours
    )
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

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def pg_enum(enum_class: type[enum.StrEnum], name: str) -> Enum:
    return Enum(enum_class, name=name, values_callable=lambda e: [m.value for m in e])


class Role(enum.StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class FeeStatus(enum.StrEnum):
    UP_TO_DATE = "up_to_date"
    OVERDUE = "overdue"


class MemberAccountState(enum.StrEnum):
    NOT_ACTIVATED = "not_activated"
    ACTIVATED = "activated"


class AdminAccountState(enum.StrEnum):
    PENDING_ACTIVATION = "pending_activation"
    ACTIVE = "active"


class Member(Base):
    """Socios del club (copia de los datos del club) y el estado de su cuenta en el sistema."""

    __tablename__ = "members"

    member_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    dni: Mapped[str] = mapped_column(String(16), unique=True)
    # Puede faltar en los datos del club: sin email no se puede activar ni entrar (HU-01).
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    fee_status: Mapped[FeeStatus] = mapped_column(
        pg_enum(FeeStatus, "fee_status"), default=FeeStatus.UP_TO_DATE
    )
    account_state: Mapped[MemberAccountState] = mapped_column(
        pg_enum(MemberAccountState, "member_account_state"),
        default=MemberAccountState.NOT_ACTIVATED,
    )


class User(Base):
    """Cuenta con la que se inicia sesión: la de un socio se crea al activarla (HU-01),
    la de un admin cuando otro admin la crea (HU-07)."""

    __tablename__ = "users"
    # Un socio que también es admin tiene dos cuentas, que pueden compartir el email.
    __table_args__ = (
        Index(
            "uq_users_admin_email",
            func.lower(text("email")),
            unique=True,
            postgresql_where=text("role = 'admin'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    member_id: Mapped[str | None] = mapped_column(
        ForeignKey("members.member_id"), unique=True
    )
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[Role] = mapped_column(pg_enum(Role, "user_role"))
    # Club al que pertenece la cuenta (decisión 34). Es de donde sale el club de los
    # endpoints del Admin: nunca de un parámetro del pedido. Toda cuenta de admin lo tiene;
    # el de las cuentas de socio todavía no se completa.
    club_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id"), index=True
    )
    # Solo pasa por `pending_activation` la cuenta de un admin (HU-07/08).
    admin_state: Mapped[AdminAccountState] = mapped_column(
        pg_enum(AdminAccountState, "admin_account_state"),
        default=AdminAccountState.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class CodePurpose(enum.StrEnum):
    LOGIN = "login"
    ACTIVATION = "activation"


class AccessCode(Base):
    """Código de 6 dígitos enviado por mail (ver app/access_codes.py)."""

    __tablename__ = "access_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    purpose: Mapped[CodePurpose] = mapped_column(pg_enum(CodePurpose, "code_purpose"))
    # Destinatario: un socio (activación o login) o una cuenta de admin (login).
    member_id: Mapped[str | None] = mapped_column(
        ForeignKey("members.member_id"), index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    # Identifica el pedido sin exponer el código: va al front y vuelve en la verificación.
    challenge_hash: Mapped[str] = mapped_column(String(64), unique=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Se completa al pedir un código nuevo: solo sirve el último.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Se completa al agotar los intentos: bloquea al destinatario por un tiempo.
    exhausted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LinkToken:
    """Columnas de un link de un solo uso enviado por mail (ver app/link_tokens.py)."""

    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Se completa cuando se manda un link nuevo al mismo destinatario: solo sirve el último.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminInvitation(LinkToken, Base):
    __tablename__ = "admin_invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    invited_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """Registro de cambios relevantes (cross-cutting, auditoría): quién, cuándo y qué cambió."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    # None cuando lo hace el sistema (por ejemplo, el seed del primer admin).
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))
    # Datos del cambio, con los valores anterior y nuevo cuando corresponde.
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

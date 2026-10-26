"""Reglas de puntaje del club (HU-27): versiones publicadas y bloqueo de la fórmula."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .auth import pg_enum, utcnow


class RulesVersionState(enum.StrEnum):
    IN_FORCE = "in_force"
    SUPERSEDED = "superseded"


class FormulaLockState(enum.StrEnum):
    UNLOCKED = "unlocked"
    LOCKED = "locked"


class RulesVersion(Base):
    """Una publicación de reglas de un club. Nunca se edita: una nueva reemplaza a la vigente."""

    __tablename__ = "rules_versions"
    __table_args__ = (
        UniqueConstraint("club_id", "number", name="uq_rules_versions_club_number"),
        # Una sola versión vigente por club, también ante publicaciones concurrentes.
        Index(
            "uq_rules_versions_in_force",
            "club_id",
            unique=True,
            postgresql_where=text("state = 'in_force'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id"), index=True
    )
    number: Mapped[int] = mapped_column(Integer)
    formula_id: Mapped[str] = mapped_column(String(64))
    formula_version: Mapped[int] = mapped_column(Integer)
    # Valores como texto decimal (`"0.6"`): nunca coma flotante.
    values: Mapped[dict[str, Any]] = mapped_column(JSONB)
    state: Mapped[RulesVersionState] = mapped_column(
        pg_enum(RulesVersionState, "rules_version_state"),
        default=RulesVersionState.IN_FORCE,
    )
    published_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    previous_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("rules_versions.id")
    )


class FormulaLock(Base):
    """Bloqueo de la fórmula de un club. Sin fila, la fórmula está desbloqueada."""

    __tablename__ = "formula_locks"

    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id"), primary_key=True
    )
    state: Mapped[FormulaLockState] = mapped_column(
        pg_enum(FormulaLockState, "formula_lock_state"),
        default=FormulaLockState.UNLOCKED,
    )
    # Motivo del último cambio de estado.
    reason: Mapped[str] = mapped_column(Text)
    changed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )

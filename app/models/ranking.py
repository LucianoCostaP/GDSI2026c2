"""Rankings calculados (HU-25): una fila por corrida y una entrada por socio."""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from .auth import pg_enum, utcnow

# Largo máximo del detalle técnico que se guarda de una falla.
MAX_ERROR_LENGTH = 1000


class RankingState(enum.StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Ranking(Base):
    """Una corrida del cálculo. Registra la versión de reglas que usó (FR-005)."""

    __tablename__ = "rankings"

    __table_args__ = (
        # Una sola corrida en curso por club, también ante pedidos concurrentes (FR-001).
        Index(
            "uq_rankings_running",
            "club_id",
            unique=True,
            postgresql_where=text("status = 'running'"),
            sqlite_where=text("status = 'running'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id"), index=True
    )
    rules_version_id: Mapped[int] = mapped_column(ForeignKey("rules_versions.id"))
    status: Mapped[RankingState] = mapped_column(
        pg_enum(RankingState, "ranking_state"), default=RankingState.RUNNING
    )
    # Fecha (hora de Buenos Aires) con la que se evaluaron ventanas y vencimientos.
    calculation_date: Mapped[date] = mapped_column(Date)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    # Desde cuándo rige el ranking: se completa al terminar la corrida (FR-004).
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    population_size: Mapped[int] = mapped_column(Integer, default=0)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    # Detalle técnico de por qué falló la corrida (para soporte; no se muestra tal cual).
    error_message: Mapped[str | None] = mapped_column(Text)

    def mark_completed(self, at: datetime) -> None:
        if self.status != RankingState.RUNNING:
            raise ValueError("Solo una corrida en curso puede completarse.")
        self.status = RankingState.COMPLETED
        self.completed_at = at

    def mark_failed(self, error_message: str) -> None:
        if self.status != RankingState.RUNNING:
            raise ValueError("Solo una corrida en curso puede fallar.")
        self.status = RankingState.FAILED
        self.error_message = error_message[:MAX_ERROR_LENGTH]


class RankingEntry(Base):
    """Puntaje de un socio en un ranking: componentes, total, posición e insumos."""

    __tablename__ = "ranking_entries"
    __table_args__ = (
        UniqueConstraint(
            "ranking_id", "socio_id", name="uq_ranking_entries_ranking_socio"
        ),
        UniqueConstraint(
            "ranking_id", "position", name="uq_ranking_entries_ranking_position"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ranking_id: Mapped[int] = mapped_column(ForeignKey("rankings.id"), index=True)
    socio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("socios.id")
    )
    position: Mapped[int] = mapped_column(Integer)
    attendance_frequency: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    attendance_distance: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    institutional: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    seniority_age: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    new_member_bonus: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    cap_adjustment: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(6, 2))
    # Insumos crudos con los que se calculó (modelo de scoring, regla 4).
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

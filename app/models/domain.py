import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .enums import ClasePartido, TipoEvento

# ==============================================================================
# MODELOS SQLALCHEMY PARA PERSISTENCIA
# ==============================================================================


class Club(Base):
    __tablename__ = "clubes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    codigo_identificador: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True
    )
    api_token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    socios: Mapped[list["Socio"]] = relationship(
        "Socio", back_populates="club", cascade="all, delete-orphan"
    )
    cargas: Mapped[list["SocioCarga"]] = relationship(
        "SocioCarga", back_populates="club", cascade="all, delete-orphan"
    )
    eventos_pendientes: Mapped[list["EventoPendienteDB"]] = relationship(
        "EventoPendienteDB", back_populates="club", cascade="all, delete-orphan"
    )
    eventos_visibles: Mapped[list["EventoVisibleDB"]] = relationship(
        "EventoVisibleDB", back_populates="club", cascade="all, delete-orphan"
    )


class Socio(Base):
    __tablename__ = "socios"
    __table_args__ = (
        UniqueConstraint("club_id", "id_externo", name="uq_socios_club_id_externo"),
        UniqueConstraint("club_id", "dni", name="uq_socios_club_dni"),
        UniqueConstraint("club_id", "numero_socio", name="uq_socios_club_numero_socio"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clubes.id", ondelete="CASCADE"),
        nullable=False,
    )
    id_externo: Mapped[str] = mapped_column(String(100), nullable=False)
    dni: Mapped[str] = mapped_column(String(50), nullable=False)
    numero_socio: Mapped[str] = mapped_column(String(50), nullable=False)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_nacimiento: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_alta: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_baja_previa: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado_cuota: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    distancia_km: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    localidad: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    fecha_modificacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    club: Mapped["Club"] = relationship("Club", back_populates="socios")


class SocioCarga(Base):
    __tablename__ = "socios_cargas"
    __table_args__ = (
        UniqueConstraint("club_id", "carga_id", name="uq_cargas_club_carga"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clubes.id", ondelete="CASCADE"),
        nullable=False,
    )
    carga_id: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    estado: Mapped[str] = mapped_column(
        String(20), default="recibiendo", nullable=False
    )
    total_paginas: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    paginas_recibidas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    desde: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hasta: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_registros: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    creados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    actualizados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    desactivados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rechazados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_mensaje: Mapped[str | None] = mapped_column(Text, nullable=True)
    iniciado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    club: Mapped["Club"] = relationship("Club", back_populates="cargas")
    paginas: Mapped[list["SocioCargaPagina"]] = relationship(
        "SocioCargaPagina", back_populates="carga", cascade="all, delete-orphan"
    )
    rechazos_items: Mapped[list["SocioCargaRechazo"]] = relationship(
        "SocioCargaRechazo", back_populates="carga", cascade="all, delete-orphan"
    )


class SocioCargaPagina(Base):
    __tablename__ = "socios_cargas_paginas"
    __table_args__ = (
        UniqueConstraint("carga_id_uuid", "pagina", name="uq_cargas_paginas"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    carga_id_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("socios_cargas.id", ondelete="CASCADE"),
        nullable=False,
    )
    pagina: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    recibido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    carga: Mapped["SocioCarga"] = relationship("SocioCarga", back_populates="paginas")


class SocioStagingCompleta(Base):
    __tablename__ = "socios_staging_completa"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    carga_id_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("socios_cargas.id", ondelete="CASCADE"),
        nullable=False,
    )
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clubes.id", ondelete="CASCADE"),
        nullable=False,
    )
    pagina: Mapped[int] = mapped_column(Integer, nullable=False)
    id_externo: Mapped[str] = mapped_column(String(100), nullable=False)
    dni: Mapped[str] = mapped_column(String(50), nullable=False)
    numero_socio: Mapped[str] = mapped_column(String(50), nullable=False)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_nacimiento: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_alta: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_baja_previa: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado_cuota: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    distancia_km: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    localidad: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fecha_modificacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    recibido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SocioCargaRechazo(Base):
    __tablename__ = "socios_cargas_rechazos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    carga_id_uuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("socios_cargas.id", ondelete="CASCADE"),
        nullable=False,
    )
    id_externo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    field: Mapped[str | None] = mapped_column(String(100), nullable=True)
    codigo: Mapped[str] = mapped_column(String(100), nullable=False)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    carga: Mapped["SocioCarga"] = relationship(
        "SocioCarga", back_populates="rechazos_items"
    )


# Modelos de eventos en SQLAlchemy para compatibilidad con ORM si se desea
class EventoPendienteDB(Base):
    __tablename__ = "eventos_pendientes_verificacion"
    __table_args__ = (
        UniqueConstraint("club_id", "id_externo", name="uq_pendientes_club_externo"),
    )

    id_interno: Mapped[str] = mapped_column(String(64), primary_key=True)
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False
    )
    id_externo: Mapped[str] = mapped_column(String(100), nullable=False)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lugar: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    es_historico: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    estado: Mapped[str] = mapped_column(
        String(50), default="pendiente_definicion_importancia", nullable=False
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    club: Mapped["Club"] = relationship("Club", back_populates="eventos_pendientes")


class EventoVisibleDB(Base):
    __tablename__ = "eventos_visibles"
    __table_args__ = (
        UniqueConstraint("club_id", "id_externo", name="uq_visibles_club_externo"),
    )

    id_interno: Mapped[str] = mapped_column(String(64), primary_key=True)
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False
    )
    id_externo: Mapped[str] = mapped_column(String(100), nullable=False)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lugar: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    clase: Mapped[str | None] = mapped_column(String(1), nullable=True)
    puntos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publicado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    club: Mapped["Club"] = relationship("Club", back_populates="eventos_visibles")


# ==============================================================================
# MODELOS DE DOMINIO LIVIANOS (DATACLASSES)
# ==============================================================================


@dataclass
class ClubDomain:
    id: str
    nombre: str
    codigo_identificador: str
    api_token: str
    activo: bool = True
    creado_en: datetime | None = None


@dataclass
class EventoBase:
    id_interno: str
    club_id: str
    id_externo: str
    titulo: str
    fecha_hora: datetime
    lugar: str
    tipo: TipoEvento
    descripcion: str | None = None


@dataclass
class EventoPendiente(EventoBase):
    es_historico: bool = False
    estado: str = "pendiente_definicion_importancia"
    creado_en: datetime | None = None
    actualizado_en: datetime | None = None


@dataclass
class EventoVisible(EventoBase):
    clase: ClasePartido | None = None
    puntos: int | None = None
    publicado_en: datetime | None = None
    actualizado_en: datetime | None = None


@dataclass
class EventoCambioPendiente:
    id_cambio: str
    id_interno: str
    club_id: str
    titulo: str
    fecha_hora: datetime
    lugar: str
    descripcion: str | None = None
    estado_revision: str = "pendiente_revision"
    solicitado_en: datetime | None = None

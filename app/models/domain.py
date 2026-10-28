import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from .enums import ClasePartido, TipoEvento

# ==============================================================================
# MODELOS SQLALCHEMY PARA PERSISTENCIA
# ==============================================================================
# Estas tablas las crea a mano la migración e7a1b2c3d4e5. Los modelos tienen que
# describirlas igual (tamaños, tipos, índices y nombres de restricciones): si no,
# `alembic revision --autogenerate` propone cambiar o borrar lo que falte.
# CI lo verifica con `alembic check`.

# Tipo ENUM creado por la migración; el modelo no lo crea ni lo borra.
TIPO_EVENTO_DB = ENUM(
    "Partido", "Institucional", "Historico", name="tipo_evento", create_type=False
)


class Club(Base):
    __tablename__ = "clubes"
    __table_args__ = (
        Index("idx_clubes_token", "api_token", postgresql_where=text("activo = TRUE")),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    codigo_identificador: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True
    )
    api_token: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
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
        Index("idx_socios_club_activo", "club_id", "activo"),
        Index("idx_socios_club_dni", "club_id", "dni"),
        Index("idx_socios_club_numero_socio", "club_id", "numero_socio"),
        Index("idx_socios_club_email", "club_id", "email"),
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
        Index("idx_socios_cargas_club_estado", "club_id", "estado"),
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
    __table_args__ = (
        Index("idx_staging_carga", "carga_id_uuid"),
        Index("idx_staging_dni", "carga_id_uuid", "dni"),
    )

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
    __table_args__ = (Index("idx_rechazos_carga", "carga_id_uuid"),)

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
        UniqueConstraint(
            "club_id", "id_externo", name="uq_eventos_pendientes_club_externo"
        ),
        Index("idx_pendientes_club_fecha", "club_id", "fecha_hora"),
        Index("idx_pendientes_club_titulo", "club_id", "titulo"),
    )

    id_interno: Mapped[str] = mapped_column(String(64), primary_key=True)
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False
    )
    id_externo: Mapped[str] = mapped_column(String(100), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lugar: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(TIPO_EVENTO_DB, nullable=False)
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
        UniqueConstraint(
            "club_id", "id_externo", name="uq_eventos_visibles_club_externo"
        ),
        Index("idx_visibles_club_fecha", "club_id", "fecha_hora"),
        Index("idx_visibles_club_titulo", "club_id", "titulo"),
    )

    id_interno: Mapped[str] = mapped_column(String(64), primary_key=True)
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False
    )
    id_externo: Mapped[str] = mapped_column(String(100), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    lugar: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(TIPO_EVENTO_DB, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    clase: Mapped[str | None] = mapped_column(String(1), nullable=True)
    puntos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # HU-22 FR-007: 'admin' o 'system', y si la clase o los puntos fueron por defecto.
    publicado_por: Mapped[str] = mapped_column(
        String(10), server_default="admin", nullable=False
    )
    es_default: Mapped[bool] = mapped_column(
        Boolean, server_default="false", nullable=False
    )
    publicado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    club: Mapped["Club"] = relationship("Club", back_populates="eventos_visibles")


class EventoCambioPendienteDB(Base):
    """Cambios de eventos publicados enviados por el club (HU-23, fuera del MVP)."""

    __tablename__ = "eventos_cambios_pendientes"
    __table_args__ = (Index("idx_cambios_evento", "id_interno", "club_id"),)

    id_cambio: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    id_interno: Mapped[str] = mapped_column(String(64), nullable=False)
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False
    )
    titulo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fecha_hora: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lugar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado_revision: Mapped[str] = mapped_column(
        String(50), server_default="pendiente_revision", nullable=False
    )
    solicitado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ==============================================================================
# MODELOS HU-24: ASISTENCIAS Y ACTIVIDADES RECURRENTES
# ==============================================================================


class CargaParticipacionDB(Base):
    """Registro maestro de cada carga de asistencia o actividades recurrentes."""

    __tablename__ = "cargas_participacion"
    __table_args__ = (
        Index("idx_cargas_part_club_tipo", "club_id", "tipo"),
        Index("idx_cargas_part_club_ext", "club_id", "carga_id_externo"),
        Index("idx_cargas_part_club_evento", "club_id", "evento_id_externo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'asistencia' / 'actividades'
    origen: Mapped[str] = mapped_column(String(10), nullable=False)  # 'club' / 'file'
    carga_id_externo: Mapped[str] = mapped_column(String(100), nullable=False)
    evento_id_externo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    estado: Mapped[str] = mapped_column(
        String(30), server_default="receiving", nullable=False
    )
    total_paginas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    paginas_recibidas: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
    total_registros: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
    registros_incorporados: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
    registros_actualizados: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
    registros_rechazados: Mapped[int] = mapped_column(
        Integer, server_default="0", nullable=False
    )
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    desde: Mapped[date | None] = mapped_column(Date, nullable=True)
    hasta: Mapped[date | None] = mapped_column(Date, nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    aprobado_por_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    motivo_fallo: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AsistenciaStagingDB(Base):
    """Almacenamiento temporal para páginas de asistencia antes de aplicarse o aprobarse."""

    __tablename__ = "asistencias_staging"
    __table_args__ = (
        Index("idx_asistencias_staging_carga_pag", "carga_id", "pagina"),
        Index("idx_asistencias_staging_carga_dni", "carga_id", "dni"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    carga_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cargas_participacion.id", ondelete="CASCADE"),
        nullable=False,
    )
    pagina: Mapped[int] = mapped_column(Integer, nullable=False)
    dni: Mapped[str] = mapped_column(String(32), nullable=False)
    numero_socio: Mapped[str | None] = mapped_column(String(32), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AsistenciaDB(Base):
    """Registro definitivo de asistencia a un evento específico del club."""

    __tablename__ = "asistencias"
    __table_args__ = (
        UniqueConstraint(
            "club_id", "evento_id_externo", "dni", name="uq_asistencias_club_evento_dni"
        ),
        Index("idx_asistencias_club_evento", "club_id", "evento_id_externo"),
        Index("idx_asistencias_club_dni", "club_id", "dni"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False
    )
    evento_id_externo: Mapped[str] = mapped_column(String(64), nullable=False)
    dni: Mapped[str] = mapped_column(String(32), nullable=False)
    numero_socio: Mapped[str | None] = mapped_column(String(32), nullable=True)
    carga_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cargas_participacion.id"), nullable=False
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ActividadRecurrenteDB(Base):
    """Registro de participación en actividades recurrentes (deporte federado o subcomisión)."""

    __tablename__ = "actividades_recurrentes"
    __table_args__ = (
        UniqueConstraint(
            "club_id",
            "dni",
            "tipo",
            "fecha_desde",
            name="uq_actividades_club_dni_tipo_desde",
        ),
        Index("idx_actividades_club_dni", "club_id", "dni"),
        Index("idx_actividades_club_tipo", "club_id", "tipo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    club_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False
    )
    dni: Mapped[str] = mapped_column(String(32), nullable=False)
    tipo: Mapped[str] = mapped_column(String(32), nullable=False)
    fecha_desde: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_hasta: Mapped[date] = mapped_column(Date, nullable=False)
    carga_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cargas_participacion.id"), nullable=False
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CargaParticipacionRechazoDB(Base):
    """Detalle de registros rechazados en una carga de asistencia o actividades."""

    __tablename__ = "cargas_participacion_rechazos"
    __table_args__ = (Index("idx_cargas_part_rechazos_carga", "carga_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    carga_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cargas_participacion.id", ondelete="CASCADE"),
        nullable=False,
    )
    dni: Mapped[str | None] = mapped_column(String(32), nullable=True)
    campo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    codigo: Mapped[str] = mapped_column(String(64), nullable=False)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    fila: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


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

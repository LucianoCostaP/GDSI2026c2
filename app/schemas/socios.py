import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ==============================================================================
# ESQUEMAS DE ERROR SEGÚN CONTRATO CLUB API
# Formato: {"error": {"code": "...", "message": "...", "field": "..."}}
# ==============================================================================


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ==============================================================================
# DETALLE DE RECHAZO INDIVIDUAL DE SOCIO
# ==============================================================================


class RechazoDetail(BaseModel):
    id_externo: str | None = None
    field: str | None = None
    codigo: str
    motivo: str


# ==============================================================================
# DATOS DE SOCIO
# ==============================================================================

EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[a-zA-Z0-9\.\-]+\.[a-zA-Z]{2,}$")


class SocioPayload(BaseModel):
    id_externo: str = Field(
        ..., min_length=1, description="Identificador único del socio en el club"
    )
    dni: str = Field(..., min_length=1, description="Documento nacional de identidad")
    numero_socio: str = Field(
        ..., min_length=1, description="Número de socio en el club"
    )
    nombre: str = Field(..., min_length=1, description="Nombre y apellido completo")
    fecha_nacimiento: date = Field(..., description="Fecha de nacimiento YYYY-MM-DD")
    fecha_alta: date = Field(..., description="Fecha de alta YYYY-MM-DD")
    fecha_baja_previa: date | None = Field(
        None, description="Fecha de baja anterior si la hubiera"
    )
    estado_cuota: Literal["al_dia", "moroso"] = Field(
        ..., description="Estado de pago de cuota"
    )
    email: str = Field(..., min_length=3, description="Correo electrónico registrado")
    distancia_km: Decimal = Field(
        ..., ge=0, description="Distancia al estadio en kilómetros"
    )
    localidad: str | None = Field(None, description="Localidad opcional")
    fecha_modificacion: datetime | None = Field(
        None, description="Timestamp ISO 8601 con offset explícito"
    )

    @field_validator("id_externo", "dni", "numero_socio", "nombre")
    @classmethod
    def check_non_empty_strings(cls, v: str, info) -> str:
        s = v.strip()
        if not s:
            raise ValueError(f"El campo '{info.field_name}' no puede estar vacío.")
        return s

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        s = v.strip()
        if not EMAIL_REGEX.match(s):
            raise ValueError("Formato de correo electrónico inválido.")
        return s

    @field_validator("fecha_modificacion")
    @classmethod
    def validate_explicit_offset(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError(
                "El timestamp debe contener un offset de zona horaria explícito o 'Z'."
            )
        return v


class SocioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_externo: str
    dni: str
    numero_socio: str
    nombre: str
    fecha_nacimiento: date
    fecha_alta: date
    fecha_baja_previa: date | None = None
    estado_cuota: str
    email: str
    distancia_km: Decimal
    localidad: str | None = None
    activo: bool
    fecha_modificacion: datetime


# ==============================================================================
# CARGA COMPLETA (SNAPSHOT PAGINADO)
# ==============================================================================


class CargaCompletaRequest(BaseModel):
    carga_id: str = Field(
        ...,
        min_length=1,
        description="Identificador único del proceso de carga completa",
    )
    pagina: int = Field(..., ge=1, description="Número de página recibida (1-based)")
    total_paginas: int = Field(
        ..., ge=1, description="Cantidad total de páginas esperadas"
    )
    socios: list[dict[str, Any]] = Field(
        ..., description="Listado de socios en esta página"
    )

    @field_validator("carga_id")
    @classmethod
    def check_carga_id(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("El campo 'carga_id' no puede estar vacío.")
        return s


class CargaCompletaResponse(BaseModel):
    carga_id: str
    pagina: int
    total_paginas: int
    estado: str
    mensaje: str
    rechazos: list[RechazoDetail] = []


# ==============================================================================
# CARGA INCREMENTAL (DELTAS / CAMBIOS)
# ==============================================================================


class CambioIncrementalItem(BaseModel):
    accion: Literal["alta", "modificacion", "baja"]
    socio: dict[str, Any] | None = None
    id_externo: str | None = None


class CargaIncrementalRequest(BaseModel):
    lote_id: str = Field(
        ..., min_length=1, description="Identificador único del lote incremental"
    )
    desde: datetime = Field(
        ..., description="Marca de agua inicial (ISO 8601 con offset)"
    )
    hasta: datetime = Field(
        ..., description="Marca de agua final (ISO 8601 con offset)"
    )
    cambios: list[CambioIncrementalItem] = Field(
        ..., description="Lista de cambios del lote"
    )

    @field_validator("lote_id")
    @classmethod
    def check_lote_id(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("El campo 'lote_id' no puede estar vacío.")
        return s

    @field_validator("desde", "hasta")
    @classmethod
    def check_offsets(cls, v: datetime, info) -> datetime:
        if v.tzinfo is None:
            raise ValueError(
                f"El timestamp '{info.field_name}' debe contener un offset de zona horaria explícito."
            )
        return v


class CargaIncrementalResponse(BaseModel):
    lote_id: str
    estado: str
    creados: int
    actualizados: int
    desactivados: int
    rechazados: int
    detalles_rechazos: list[RechazoDetail] = []


# ==============================================================================
# ESTADO DE CARGA Y AUDITORÍA
# ==============================================================================


class CargaStatusResponse(BaseModel):
    carga_id: str
    tipo: str
    estado: str
    iniciado_en: datetime
    completado_en: datetime | None = None
    pagina_actual: int
    total_paginas: int
    paginas_recibidas: int
    total_registros: int
    creados: int
    actualizados: int
    desactivados: int
    rechazados: int
    detalles_rechazos: list[RechazoDetail] = []
    error_mensaje: str | None = None


# ==============================================================================
# FRESCURA DEL PADRÓN (HU-43 / FR-008)
# ==============================================================================


class FreshnessResponse(BaseModel):
    club_id: str
    club_nombre: str
    ultima_carga_exitosa: datetime | None
    antiguedad_horas: float | None
    limite_horas: int
    esta_desactualizado: bool
    advertencia: str | None = None

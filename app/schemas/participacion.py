from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RechazoParticipacionDetail(BaseModel):
    dni: str | None = None
    field: str | None = None
    codigo: str
    motivo: str
    fila: int | None = None


# ==============================================================================
# ASISTENCIA A EVENTOS (PUSH DEL CLUB)
# ==============================================================================


class AsistenciaRegistro(BaseModel):
    dni: str = Field(
        ..., min_length=1, max_length=32, description="DNI del socio que asistió"
    )
    numero_socio: str | None = Field(
        None,
        max_length=32,
        description="Número de socio para validación cruzada con DNI",
    )


class CargaAsistenciaPageRequest(BaseModel):
    carga_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Identificador único de la carga asignado por el club",
    )
    pagina: int = Field(
        ..., ge=1, description="Número secuencial de la página (base 1)"
    )
    total_paginas: int = Field(
        ..., ge=1, description="Cantidad total de páginas de la carga"
    )
    registros: list[AsistenciaRegistro] = Field(
        ...,
        max_length=10000,
        description="Registros de asistencia contenidos en la página",
    )


class CargaAsistenciaResponse(BaseModel):
    carga_id: str
    evento_id_externo: str
    pagina: int
    total_paginas: int
    estado: str
    total_registros_pagina: int
    registros_validos_pagina: int
    registros_rechazados_pagina: int
    rechazos: list[RechazoParticipacionDetail] = []
    mensaje: str | None = None


# ==============================================================================
# ACTIVIDADES RECURRENTES (PUSH DEL CLUB)
# ==============================================================================


class ActividadRegistro(BaseModel):
    dni: str = Field(..., min_length=1, max_length=32, description="DNI del socio")
    tipo: str = Field(
        ...,
        description="Tipo de actividad recurrente: 'deporte_federado' o 'subcomision'",
    )
    fecha_desde: date = Field(..., description="Fecha de inicio (YYYY-MM-DD)")
    fecha_hasta: date = Field(..., description="Fecha de fin (YYYY-MM-DD)")


class CargaActividadesBatchRequest(BaseModel):
    lote_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Identificador único del lote incremental",
    )
    desde: date = Field(..., description="Inicio del período de cambios enviados")
    hasta: date = Field(..., description="Fin del período de cambios enviados")
    registros: list[ActividadRegistro] = Field(
        ...,
        max_length=10000,
        description="Registros de actividades modificados en el período",
    )


class CargaActividadesResponse(BaseModel):
    lote_id: str
    estado: str
    total_registros: int
    registros_incorporados: int
    registros_actualizados: int
    registros_rechazados: int
    rechazos: list[RechazoParticipacionDetail] = []
    mensaje: str | None = None


# ==============================================================================
# CONSULTA DE ESTADO DE CARGAS
# ==============================================================================


class CargaParticipacionStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    carga_id: str
    tipo: str
    origen: str
    evento_id_externo: str | None = None
    estado: str
    total_paginas: int | None = None
    paginas_recibidas: int
    total_registros: int
    registros_incorporados: int
    registros_actualizados: int
    registros_rechazados: int
    desde: date | None = None
    hasta: date | None = None
    creado_en: datetime
    actualizado_en: datetime
    rechazos: list[RechazoParticipacionDetail] = []
    motivo_fallo: str | None = None


# ==============================================================================
# GESTIÓN DE ADMINISTRACIÓN (CSV, APROBACIONES, EVENTOS ELEGIBLES)
# ==============================================================================


class EventoElegibleAsistenciaResponse(BaseModel):
    id_interno: str
    id_externo: str
    titulo: str
    tipo: str
    fecha_hora: datetime
    lugar: str
    tiene_asistencia_previa: bool
    asistencia_previa_info: dict[str, Any] | None = None


class CargaPreviaInfo(BaseModel):
    carga_id: str
    fecha: datetime
    origen: str
    responsable: str | None = None
    total_registros: int


class CargaPendienteAprobacionResponse(BaseModel):
    carga_id: str
    evento_id_externo: str
    evento_titulo: str | None = None
    fecha_evento: datetime | None = None
    origen: str
    registros_a_incorporar: int
    creado_en: datetime
    carga_previa: CargaPreviaInfo | None = None


class AprobacionAccionResponse(BaseModel):
    carga_id: str
    evento_id_externo: str | None = None
    estado: str
    mensaje: str


class UploadCSVResponse(BaseModel):
    carga_id: str
    tipo: str
    evento_id_externo: str | None = None
    estado: str
    total_registros: int
    registros_incorporados: int
    registros_actualizados: int
    registros_rechazados: int
    rechazos: list[RechazoParticipacionDetail] = []
    requiere_confirmacion_reemplazo: bool = False
    carga_previa: CargaPreviaInfo | None = None
    mensaje: str | None = None

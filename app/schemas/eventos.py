from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..models.enums import ClasePartido, TipoEvento


class EventoCreateRequest(BaseModel):
    """
    Payload para la creación individual o en lote de eventos.
    Todos los campos esenciales son obligatorios según contrato.
    """

    id_externo: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Identificador original del evento en el club",
    )
    titulo: str = Field(
        ..., min_length=1, max_length=255, description="Título del evento"
    )
    fecha_hora: datetime = Field(
        ..., description="Fecha y hora en formato ISO 8601 (ej: 2026-11-20T17:00:00Z)"
    )
    lugar: str = Field(
        ..., min_length=1, max_length=255, description="Lugar o dirección del evento"
    )
    tipo: TipoEvento = Field(
        ..., description="Tipo de evento: 'Partido', 'Institucional' o 'Historico'"
    )
    descripcion: str | None = Field(None, description="Descripción contextual opcional")
    es_historico: bool | None = Field(
        False, description="Flag opcional para registrar eventos ya finalizados"
    )

    model_config = ConfigDict(
        use_enum_values=True,
        json_schema_extra={
            "example": {
                "id_externo": "EVT-1029",
                "titulo": "Partido vs Rivales FC",
                "fecha_hora": "2026-11-20T17:00:00Z",
                "lugar": "Estadio Visitante, calle ejemplo 1234",
                "tipo": "Partido",
                "descripcion": "Fecha 12 del torneo local",
                "es_historico": False,
            }
        },
    )


class EventoCreateResponse(BaseModel):
    mensaje: str = "Evento creado exitosamente."
    id_interno: str


class EventoDetailResponse(BaseModel):
    id_interno: str
    id_externo: str
    titulo: str
    fecha_hora: datetime
    lugar: str
    tipo: str
    descripcion: str | None = None
    estado_ciclo: str = "pendiente_definicion_importancia"
    clase: str | None = None
    puntos: int | None = None
    creado_en: datetime | None = None
    actualizado_en: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class BatchSuccessItem(BaseModel):
    id_externo: str
    id_interno: str
    estado: str = "creado"


class BatchOmittedItem(BaseModel):
    id_externo: str
    motivo: str = (
        "Evento ya registrado previamente (omitido de forma segura por idempotencia)."
    )
    estado: str = "omitido"


class BatchFailedItem(BaseModel):
    id_externo: str | None = None
    error: str
    codigo: int


class BatchSummary(BaseModel):
    total: int
    creados: int
    omitidos: int
    fallidos: int
    exitosos: int | None = None

    def model_post_init(self, __context: Any, /) -> None:
        if self.exitosos is None:
            self.exitosos = self.creados


class BatchResponse(BaseModel):
    """
    Estructura de respuesta 207 Multi-Status para cargas masivas (Batch y Batch Históricos).
    """

    resumen: BatchSummary
    creados: list[BatchSuccessItem]
    exitosos: list[BatchSuccessItem]
    omitidos: list[BatchOmittedItem] = []
    fallidos: list[BatchFailedItem] = []


# ==============================================================================
# ESQUEMAS PARA HU-17: CONSULTA DE PRÓXIMOS EVENTOS (SOCIO)
# ==============================================================================


class ProximoEventoItem(BaseModel):
    id: str = Field(..., description="Identificador único del evento (id_interno)")
    id_interno: str = Field(..., description="Identificador interno del evento")
    id_externo: str = Field(..., description="Identificador provisto por el club")
    titulo: str = Field(..., description="Título del evento")
    fecha_hora: datetime = Field(
        ..., description="Fecha y hora de inicio en UTC (ISO 8601)"
    )
    fecha: str = Field(
        ...,
        description="Fecha formateada en horario local de Buenos Aires (YYYY-MM-DD)",
    )
    hora: str = Field(
        ..., description="Hora formateada en horario local de Buenos Aires (HH:MM)"
    )
    lugar: str = Field(..., description="Lugar / estadio del evento")
    tipo: str = Field(
        ...,
        description="Tipo de evento: 'Partido' o 'Evento institucional/amateur'",
    )
    descripcion: str | None = Field(None, description="Descripción opcional del evento")
    slot_url: str = Field(
        ...,
        description="Enlace para consultar el turno propio de reserva para este evento (HU-39)",
    )

    model_config = ConfigDict(from_attributes=True)


class ProximosEventosResponse(BaseModel):
    total: int = Field(0, description="Cantidad total de próximos eventos publicados")
    eventos: list[ProximoEventoItem] = Field(
        default_factory=list,
        description="Lista de eventos ordenados cronológicamente (el más próximo primero)",
    )
    mensaje: str | None = Field(
        None,
        description="Mensaje informativo cuando no hay eventos próximos publicados (HU-17)",
    )


# ==============================================================================
# ESQUEMAS PARA HU-22: DEFINICIÓN DE IMPORTANCIA Y PUBLICACIÓN DE EVENTOS (ADMIN)
# ==============================================================================


class ClaseInfoResponse(BaseModel):
    clase: ClasePartido = Field(..., description="Clase A, B o C")
    factor: float = Field(..., description="Factor de ponderación de asistencia")
    demanda: str = Field(
        ..., description="Nivel de demanda esperada ('alta', 'regular', 'baja')"
    )
    es_default: bool = Field(
        ..., description="Indica si es la clase predeterminada del sistema"
    )
    descripcion: str = Field(..., description="Descripción del significado y factor")


class EventoPendientePublicacionResponse(BaseModel):
    id_interno: str = Field(..., description="Identificador interno del evento")
    id_externo: str = Field(..., description="Identificador provisto por el club")
    titulo: str = Field(..., description="Título del evento")
    fecha_hora: datetime = Field(..., description="Fecha y hora de inicio (UTC)")
    lugar: str = Field(..., description="Lugar / sede del evento")
    tipo: str = Field(..., description="Tipo de evento: 'Partido' o 'Institucional'")
    descripcion: str | None = Field(None, description="Descripción opcional")
    creado_en: datetime = Field(
        ..., description="Momento de importación / recepción del evento"
    )
    deadline_publicacion: datetime = Field(
        ..., description="Fecha límite de publicación automática"
    )
    segundos_restantes_deadline: int = Field(
        ..., description="Segundos restantes para alcanzar el deadline"
    )
    plazo_expirado: bool = Field(
        ..., description="Indica si el deadline ya fue alcanzado o superado"
    )

    model_config = ConfigDict(from_attributes=True)


class PublicarEventoRequest(BaseModel):
    clase: ClasePartido | None = Field(
        None,
        description="Clase para Partidos ('A', 'B' o 'C'). No aplicable a eventos institucionales.",
    )
    puntos: int | None = Field(
        None,
        ge=1,
        le=100,
        description="Puntos enteros de 1 a 100 para Eventos Institucionales. No aplicable a Partidos.",
    )


class PublicarEventoResponse(BaseModel):
    mensaje: str = "Evento publicado exitosamente."
    id_interno: str
    tipo: str
    clase: str | None = None
    puntos: int | None = None
    publicado_en: datetime
    publicado_por: str = "admin"
    es_default: bool = False


class AutoPublishResponse(BaseModel):
    mensaje: str = "Proceso de publicación automática completado."
    procesados: int
    publicados: int
    omitidos: int
    eventos_publicados: list[str]

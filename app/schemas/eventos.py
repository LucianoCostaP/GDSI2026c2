from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..models.enums import TipoEvento


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

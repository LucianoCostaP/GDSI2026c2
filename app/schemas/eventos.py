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
    detalle: list[PublicarEventoResponse] = []


# ==============================================================================
# ESQUEMAS PARA HU-23: REPROGRAMACIÓN, RETIRO Y RESTAURACIÓN DE EVENTOS
# ==============================================================================


class ClubEventoUpdateRequest(BaseModel):
    titulo: str | None = Field(None, max_length=255)
    fecha_hora: datetime | None = None
    lugar: str | None = Field(None, max_length=255)
    tipo: str | None = None
    descripcion: str | None = None


class ClubCancelacionRequest(BaseModel):
    motivo: str | None = Field(None, max_length=500)


class ComparacionValores(BaseModel):
    fecha_hora_actual: datetime
    fecha_hora_nueva: datetime | None = None
    lugar_actual: str
    lugar_nuevo: str | None = None
    titulo_actual: str
    titulo_nuevo: str | None = None
    descripcion_actual: str | None = None
    descripcion_nueva: str | None = None


class EventoCambioReviewResponse(BaseModel):
    id_cambio: str
    id_interno: str
    id_externo: str
    club_id: str
    titulo: str
    tipo: str
    estado: str
    solicitado_en: datetime
    valores_previos: dict[str, Any]
    valores_nuevos: dict[str, Any]
    comparacion: ComparacionValores

    model_config = ConfigDict(from_attributes=True)


class EventoCambioActionResponse(BaseModel):
    mensaje: str
    id_cambio: str
    id_interno: str
    estado: str
    fin_ajuste_clase_puntos: datetime | None = None
    advertencia_cronograma: str | None = None


class EventoRetiroRequest(BaseModel):
    """Descarte de un evento pendiente (HU-21)."""

    motivo: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Motivo obligatorio del descarte del evento",
    )


class EventoRetiroResponse(BaseModel):
    mensaje: str = "Evento retirado exitosamente."
    id_interno: str
    estado: str = "withdrawn"
    retirado_en: datetime
    motivo: str


class WithdrawRequest(BaseModel):
    """Retiro definitivo de un evento publicado (HU-23B US5)."""

    # La confirmación explícita del Admin (escenario 1): sin ella, `CONFIRMATION_REQUIRED`.
    confirmed: bool = False
    # La `version` del listado: si otro Admin cambió el evento, `EVENT_CHANGED` (escenario 10).
    expected_version: int


class WithdrawOut(BaseModel):
    id_interno: str
    estado: str = "withdrawn"
    segmentation_deleted: bool
    schedule_deleted: bool


class EventoRestaurarResponse(BaseModel):
    mensaje: str = "Evento restaurado exitosamente."
    id_interno: str
    estado: str = "publicado"
    restaurado_en: datetime


class EventoAjustarClaseRequest(BaseModel):
    clase: ClasePartido | None = Field(
        None, description="Nueva clase (A, B o C) para Partido"
    )
    puntos: int | None = Field(
        None, ge=1, le=100, description="Nuevos puntos para Institucional"
    )


class EventoAjustarClaseResponse(BaseModel):
    mensaje: str = "Clase/puntos ajustados exitosamente."
    id_interno: str
    clase: str | None = None
    puntos: int | None = None
    actualizado_en: datetime


# ==============================================================================
# HU-23B: eventos publicados para reprogramar o retirar
# ==============================================================================


class PublishedScheduleOut(BaseModel):
    """Resumen del cronograma de olas (HU-37) de un Partido publicado."""

    status: str
    opening_at: datetime
    # Cierre general vigente: el ajustado por una reprogramación, si la hubo (HU-23B US3).
    closing_at: datetime
    # Última ola separada tras una fusión: las siguientes abren con ella. `null` si no hubo.
    merged_into_order: int | None = None
    # Una reprogramación movió el cierre o fusionó olas ("ajustado" en el listado, US1).
    adjusted: bool = False


class PublishedEventOut(BaseModel):
    """Un evento publicado que todavía no empezó (HU-23B US1)."""

    id_interno: str
    id_externo: str
    titulo: str
    tipo: TipoEvento
    fecha_hora: datetime
    lugar: str
    # Se muestra de solo lectura en el formulario de reprogramación (US2, escenario 1).
    descripcion: str | None
    # Clase (Partido) o puntos (institucional/amateur): el otro va en null.
    clase: str | None
    puntos: int | None
    cancelado_por_el_club: bool
    # La que el Admin manda al reprogramar o retirar (FR-011).
    version: int
    schedule: PublishedScheduleOut | None


class ReschedulePreviewRequest(BaseModel):
    """Fecha y hora nueva de un evento publicado (HU-23B US2): lo único editable.

    Cualquier otro campo (tipo, clase, puntos, título, lugar, descripción…) se rechaza con
    `FIELD_NOT_EDITABLE` (escenario 3), por eso se aceptan campos extra y se revisan en el
    servicio en vez de ignorarlos. La fecha llega como texto para responder un formato
    inválido con el motivo en español (`INVALID_DATETIME`, escenario 6); sin zona horaria se
    lee en Buenos Aires.
    """

    model_config = ConfigDict(extra="allow")

    fecha_hora: str | None = None


class RescheduleRequest(ReschedulePreviewRequest):
    """Reprogramación confirmada (HU-23B US2)."""

    # La `version` del listado: si otro Admin cambió el evento, `EVENT_CHANGED` (escenario 9).
    expected_version: int
    # El efecto que mostró la vista previa (escenario 7). Si llega y ya no es el mismo, la
    # reprogramación falla con `EVENT_CHANGED` en vez de aplicar otro.
    expected_schedule_effect: str | None = None
    expected_merged_into_order: int | None = None


class MovedWaveOut(BaseModel):
    order: int
    socios: int


class RescheduleNotificationsOut(BaseModel):
    """Cuántos socios reciben cada aviso (cuentas activadas)."""

    event_rescheduled: int
    # Avisos de turno de HU-23B US4, a los socios de las olas movidas: uno u otro, según si
    # la ola a la que se suman ya abrió.
    wave_rescheduled: int = 0
    wave_opened: int = 0


class RescheduleImpactOut(BaseModel):
    """Qué le pasa al cronograma con la reprogramación (HU-23B US2 escenario 7, US3)."""

    previous_fecha_hora: datetime
    new_fecha_hora: datetime
    # `no_schedule`, `none`, `closing_adjusted`, `waves_merged` o `invalidated`.
    schedule_effect: str
    previous_closing_at: datetime | None
    new_closing_at: datetime | None
    merged_into_order: int | None
    moved_waves: list[MovedWaveOut]
    # Hora de inicio de la ola a la que se suman las olas movidas, y si ya abrió.
    target_wave_starts_at: datetime | None
    target_wave_open: bool
    notifications: RescheduleNotificationsOut


class RescheduleOut(PublishedEventOut):
    """El evento reprogramado, la reprogramación y el efecto aplicado."""

    id_reprogramacion: str
    impact: RescheduleImpactOut

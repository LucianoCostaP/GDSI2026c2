"""HU-15: respuesta del historial de eventos del Socio."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EventHistoryItemOut(BaseModel):
    """Un evento del historial. No admite campos extra: la clase de un Partido no se expone."""

    model_config = ConfigDict(extra="forbid")

    id_interno: str
    titulo: str
    fecha_hora: datetime = Field(
        description="Inicio del evento en UTC; el front lo muestra en hora de Buenos Aires."
    )
    tipo: str = Field(description="`Partido` o `Evento institucional/amateur`.")


class EventHistoryResponse(BaseModel):
    """Historial de eventos del Socio, del más reciente al más antiguo."""

    model_config = ConfigDict(extra="forbid")

    total: int
    events: list[EventHistoryItemOut]

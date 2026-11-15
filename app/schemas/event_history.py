"""HU-15: respuesta del historial de eventos del Socio y de una versión de reglas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RulesRefOut(BaseModel):
    """Versión de reglas vigente al inicio de un evento y el enlace para leerla."""

    model_config = ConfigDict(extra="forbid")

    number: int
    published_at: datetime
    url: str = Field(description="`/member/scoring/rules/{number}`.")


class EventHistoryItemOut(BaseModel):
    """Un evento del historial. No admite campos extra: la clase de un Partido no se expone."""

    model_config = ConfigDict(extra="forbid")

    id_interno: str
    titulo: str
    fecha_hora: datetime = Field(
        description="Inicio del evento en UTC; el front lo muestra en hora de Buenos Aires."
    )
    tipo: str = Field(description="`Partido` o `Evento institucional/amateur`.")
    rules_version: RulesRefOut | None = Field(
        description="`null` si el evento fue antes de la primera publicación de reglas."
    )
    rules_message: str | None = Field(
        description="Texto para el socio cuando `rules_version` es `null`."
    )


class EventHistoryResponse(BaseModel):
    """Historial de eventos del Socio, del más reciente al más antiguo."""

    model_config = ConfigDict(extra="forbid")

    total: int
    events: list[EventHistoryItemOut]


class FormulaRefOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: int
    name: str


class MemberRulesVersionOut(BaseModel):
    """Una versión de reglas del club del Socio. Nunca incluye quién la publicó."""

    model_config = ConfigDict(extra="forbid")

    rules_version: int
    published_at: datetime
    in_force: bool
    formula: FormulaRefOut
    explanation: dict[str, Any] = Field(
        description="La misma explicación que HU-13 y la vista previa de HU-27."
    )

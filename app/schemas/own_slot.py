"""Respuesta del turno propio del Socio (HU-39)."""

import enum
from datetime import datetime

from pydantic import BaseModel


class OwnSlotStatus(enum.StrEnum):
    NO_TURNS = "no_turns"
    NO_SCHEDULE = "no_schedule"
    NO_WAVE = "no_wave"
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"


class OwnSlotEventOut(BaseModel):
    id_interno: str
    titulo: str
    fecha_hora: datetime
    lugar: str
    tipo: str


class OwnWaveOut(BaseModel):
    order: int
    total: int


class OwnSlotOut(BaseModel):
    event: OwnSlotEventOut
    status: OwnSlotStatus
    message: str | None = None
    wave: OwnWaveOut | None = None
    starts_at: datetime | None = None
    closing_at: datetime | None = None
    seconds_until_start: int | None = None
    seconds_until_closing: int | None = None
    now: datetime

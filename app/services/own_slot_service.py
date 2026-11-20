"""Turno propio del Socio (HU-39): su ola y cuándo se le habilita la reserva.

La ola sale de la posición del Socio en la versión del ranking de la segmentación (HU-36), no
del ranking vigente ni de la cuota actual: así no cambia con recálculos ni con pagos
posteriores (escenario 7).
"""

import math
import uuid
from datetime import datetime

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.date_utils import asegurar_utc, formatear_tipo_evento
from ..models import EventoVisibleDB, RankingEntry, User, WaveSegmentation
from ..schemas.own_slot import OwnSlotEventOut, OwnSlotOut, OwnSlotStatus, OwnWaveOut
from ..scoring.wave_schedule import (
    WaveState,
    effective_order,
    effective_wave_starts,
    wave_state,
)
from ..scoring.waves import build_waves, wave_of
from .formula_service import error
from .ranking_service import socio_of
from .wave_schedule_service import visible_schedule

NO_TURNS_MESSAGE = "Este evento no tiene turnos de reserva."
NO_SCHEDULE_MESSAGE = (
    "El cronograma de reservas de este evento todavía no está definido."
)
NO_WAVE_MESSAGE = "No tenés un turno asignado para este evento. Contactá al club."
CLOSED_MESSAGE = "El período de reserva de este evento terminó."
# HU-23B US5 escenario 6: el mismo texto venga de un enlace viejo o de una notificación.
WITHDRAWN_MESSAGE = "Este evento fue suspendido."

_SOCIO_EVENT_TYPES = {"Partido", "Institucional"}


def _visible_event(db: Session, club_id: uuid.UUID, event_id: str) -> EventoVisibleDB:
    event = db.get(EventoVisibleDB, event_id)
    if (
        event is None
        or event.club_id != club_id
        or event.tipo not in _SOCIO_EVENT_TYPES
    ):
        raise error(
            status.HTTP_404_NOT_FOUND, "EVENT_NOT_FOUND", "No encontramos este evento."
        )
    return event


def _seconds_until(moment: datetime, now: datetime) -> int:
    return math.ceil((moment - now).total_seconds())


def _position(
    db: Session, member: User, club_id: uuid.UUID, segmentation: WaveSegmentation
) -> int | None:
    socio = socio_of(db, member, club_id)
    if socio is None:
        return None
    return db.scalar(
        select(RankingEntry.position).where(
            RankingEntry.ranking_id == segmentation.ranking_id,
            RankingEntry.socio_id == socio.id,
        )
    )


def own_slot(
    db: Session, member: User, club_id: uuid.UUID, event_id: str, now: datetime
) -> OwnSlotOut:
    now = asegurar_utc(now)
    event = _visible_event(db, club_id, event_id)
    event_out = OwnSlotEventOut(
        id_interno=event.id_interno,
        titulo=event.titulo,
        fecha_hora=asegurar_utc(event.fecha_hora),
        lugar=event.lugar,
        tipo=formatear_tipo_evento(event.tipo),
    )

    if event.estado in ("withdrawn", "retirado"):
        return OwnSlotOut(
            event=event_out,
            now=now,
            status=OwnSlotStatus.WITHDRAWN,
            message=WITHDRAWN_MESSAGE,
        )

    if event.tipo != "Partido":
        return OwnSlotOut(
            event=event_out,
            now=now,
            status=OwnSlotStatus.NO_TURNS,
            message=NO_TURNS_MESSAGE,
        )

    schedule = visible_schedule(db, event.id_interno)
    if schedule is None:
        return OwnSlotOut(
            event=event_out,
            now=now,
            status=OwnSlotStatus.NO_SCHEDULE,
            message=NO_SCHEDULE_MESSAGE,
        )

    segmentation = db.get_one(WaveSegmentation, schedule.segmentation_id)
    opening = asegurar_utc(schedule.opening_at)
    closing = asegurar_utc(schedule.effective_closing)
    generated = len(
        build_waves(segmentation.ranked_total, segmentation.percentile_step)
    )
    merged_into = schedule.merged_into_order
    # Tras una fusión (HU-23B US3) el Socio ve la ola a la que se sumó, "Ola k de M", con M
    # las olas que quedaron separadas, y la hora de inicio de esa ola.
    total = merged_into if merged_into is not None else generated
    position = _position(db, member, club_id, segmentation)
    wave = (
        wave_of(position, segmentation.ranked_total, segmentation.percentile_step)
        if position is not None
        else None
    )
    order = effective_order(wave, merged_into) if wave is not None else None
    starts_at = (
        effective_wave_starts(
            opening, asegurar_utc(schedule.closing_at), generated, merged_into
        )[wave - 1]
        if wave is not None
        else None
    )

    def out(
        status: OwnSlotStatus,
        message: str | None = None,
        *,
        seconds_until_start: int | None = None,
        seconds_until_closing: int | None = None,
    ) -> OwnSlotOut:
        return OwnSlotOut(
            event=event_out,
            now=now,
            status=status,
            message=message,
            wave=OwnWaveOut(order=order, total=total) if order is not None else None,
            starts_at=starts_at,
            closing_at=closing,
            seconds_until_start=seconds_until_start,
            seconds_until_closing=seconds_until_closing,
        )

    if now >= closing:
        return out(OwnSlotStatus.CLOSED, CLOSED_MESSAGE)
    if starts_at is None:
        return out(OwnSlotStatus.NO_WAVE, NO_WAVE_MESSAGE)
    seconds_until_closing = _seconds_until(closing, now)
    if wave_state(starts_at, closing, now) == WaveState.PENDING:
        return out(
            OwnSlotStatus.PENDING,
            seconds_until_start=_seconds_until(starts_at, now),
            seconds_until_closing=seconds_until_closing,
        )
    return out(OwnSlotStatus.OPEN, seconds_until_closing=seconds_until_closing)

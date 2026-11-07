"""Cronograma de habilitación de las olas de un Partido (HU-37).

El servicio recibe `now` solo para los tests; si no llega, manda el reloj del servidor.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..core.date_utils import asegurar_utc
from ..models import (
    EventoVisibleDB,
    User,
    WaveSchedule,
    WaveScheduleStatus,
    WaveSegmentation,
    utcnow,
)
from ..scoring.wave_schedule import (
    ScheduledWave,
    WaveState,
    schedule_waves,
    validate_period,
    wave_states,
)
from ..scoring.waves import build_waves
from . import segmentation_service
from .formula_service import error


@dataclass(frozen=True)
class ScheduleView:
    schedule: WaveSchedule
    event: EventoVisibleDB
    generated_by: str
    confirmed_by: str | None
    waves: list[ScheduledWave]
    # Estado de cada ola con el reloj del servidor; `None` mientras no está confirmado,
    # porque un borrador o un cronograma invalidado no abre ninguna ola.
    states: list[WaveState | None]


def _now(now: datetime | None) -> datetime:
    return asegurar_utc(now or utcnow())


def _view(db: Session, schedule: WaveSchedule, now: datetime) -> ScheduleView:
    segmentation = db.get_one(WaveSegmentation, schedule.segmentation_id)
    closing_at = asegurar_utc(schedule.closing_at)
    waves = schedule_waves(
        build_waves(segmentation.ranked_total, segmentation.percentile_step),
        asegurar_utc(schedule.opening_at),
        closing_at,
    )
    states: list[WaveState | None] = (
        list(wave_states([w.starts_at for w in waves], closing_at, now))
        if schedule.status == WaveScheduleStatus.CONFIRMED
        else [None] * len(waves)
    )
    return ScheduleView(
        schedule=schedule,
        event=db.get_one(EventoVisibleDB, schedule.event_id),
        generated_by=db.get_one(User, schedule.generated_by_id).name,
        confirmed_by=(
            db.get_one(User, schedule.confirmed_by_id).name
            if schedule.confirmed_by_id is not None
            else None
        ),
        waves=waves,
        states=states,
    )


def _audit_values(schedule: WaveSchedule) -> dict[str, Any]:
    return {
        "segmentation_id": schedule.segmentation_id,
        "opening_at": asegurar_utc(schedule.opening_at).isoformat(),
        "closing_at": asegurar_utc(schedule.closing_at).isoformat(),
    }


def _schedule_of(
    db: Session, club_id: uuid.UUID, event_id: str, *, for_update: bool = False
) -> WaveSchedule:
    query = select(WaveSchedule).where(
        WaveSchedule.event_id == event_id,
        WaveSchedule.club_id == club_id,
    )
    schedule = db.scalar(query.with_for_update() if for_update else query)
    if schedule is None:
        raise error(
            status.HTTP_404_NOT_FOUND,
            "SCHEDULE_NOT_FOUND",
            "Este partido todavía no tiene cronograma.",
        )
    return schedule


def get_schedule(
    db: Session, club_id: uuid.UUID, event_id: str, now: datetime | None = None
) -> ScheduleView:
    return _view(db, _schedule_of(db, club_id, event_id), _now(now))


def visible_schedule(db: Session, event_id: str) -> WaveSchedule | None:
    """El cronograma que pueden ver los socios (HU-39): solo el confirmado (SC-003)."""
    return db.scalar(
        select(WaveSchedule).where(
            WaveSchedule.event_id == event_id,
            WaveSchedule.status == WaveScheduleStatus.CONFIRMED,
        )
    )


def _segmentation_required(db: Session, event: EventoVisibleDB) -> WaveSegmentation:
    """Las olas del Partido (escenario 1): sin ellas no hay nada que programar."""
    segmentation = db.scalar(
        select(WaveSegmentation).where(WaveSegmentation.event_id == event.id_interno)
    )
    if segmentation is None:
        raise error(
            status.HTTP_409_CONFLICT,
            "SEGMENTATION_REQUIRED",
            "Este partido todavía no tiene olas: generalas antes de armar el cronograma.",
        )
    return segmentation


def _validated_period(
    event: EventoVisibleDB,
    segmentation: WaveSegmentation,
    opening_at: datetime,
    closing_at: datetime,
    now: datetime,
) -> None:
    """Rechaza el período con el motivo (escenario 2, FR-005)."""
    violation = validate_period(
        opening=opening_at,
        closing=closing_at,
        event_start=asegurar_utc(event.fecha_hora),
        waves=len(build_waves(segmentation.ranked_total, segmentation.percentile_step)),
        now=now,
        min_step_minutes=settings.wave_min_step_minutes,
    )
    if violation is not None:
        raise error(
            status.HTTP_422_UNPROCESSABLE_CONTENT, violation.code, violation.message
        )


def generate(
    db: Session,
    admin: User,
    club_id: uuid.UUID,
    event_id: str,
    *,
    opening_at: datetime,
    closing_at: datetime,
    now: datetime | None = None,
) -> ScheduleView:
    """Genera el cronograma del Partido en borrador."""
    current = _now(now)
    opening_at = asegurar_utc(opening_at)
    closing_at = asegurar_utc(closing_at)
    event = segmentation_service.upcoming_partido(
        db,
        club_id,
        event_id,
        current,
        action="armar el cronograma",
        started="no se puede generar el cronograma",
    )
    segmentation = _segmentation_required(db, event)
    _validated_period(event, segmentation, opening_at, closing_at, current)

    schedule = WaveSchedule(
        club_id=club_id,
        event_id=event.id_interno,
        segmentation_id=segmentation.id,
        opening_at=opening_at,
        closing_at=closing_at,
        status=WaveScheduleStatus.DRAFT,
        generated_at=utcnow(),
        generated_by_id=admin.id,
    )
    db.add(schedule)
    db.flush()

    audit.record(
        db,
        "wave_schedule.generated",
        actor_id=admin.id,
        entity="wave_schedule",
        entity_id=schedule.id,
        event_id=event.id_interno,
        new=_audit_values(schedule),
    )
    db.commit()
    return _view(db, schedule, current)


def confirm(
    db: Session,
    admin: User,
    club_id: uuid.UUID,
    event_id: str,
    *,
    now: datetime | None = None,
) -> ScheduleView:
    """Confirma el borrador: desde ahí lo ven los socios (escenario 4, FR-006)."""
    current = _now(now)
    schedule = _schedule_of(db, club_id, event_id, for_update=True)
    if schedule.status == WaveScheduleStatus.CONFIRMED:
        raise error(
            status.HTTP_409_CONFLICT,
            "SCHEDULE_ALREADY_CONFIRMED",
            "El cronograma ya está confirmado.",
        )
    if asegurar_utc(schedule.opening_at) <= current:
        raise error(
            status.HTTP_409_CONFLICT,
            "OPENING_ALREADY_PASSED",
            "La apertura ya pasó: regenerá el cronograma con otro período.",
        )

    schedule.status = WaveScheduleStatus.CONFIRMED
    schedule.confirmed_at = utcnow()
    schedule.confirmed_by_id = admin.id
    audit.record(
        db,
        "wave_schedule.confirmed",
        actor_id=admin.id,
        entity="wave_schedule",
        entity_id=schedule.id,
        event_id=schedule.event_id,
        new=_audit_values(schedule),
    )
    db.commit()
    return _view(db, schedule, current)

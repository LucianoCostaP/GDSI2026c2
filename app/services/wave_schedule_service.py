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
from ..scoring.wave_schedule import validate_period
from ..scoring.waves import build_waves
from . import segmentation_service
from .formula_service import error


@dataclass(frozen=True)
class ScheduleView:
    schedule: WaveSchedule
    event: EventoVisibleDB
    generated_by: str


def _now(now: datetime | None) -> datetime:
    return asegurar_utc(now or utcnow())


def _view(db: Session, schedule: WaveSchedule) -> ScheduleView:
    return ScheduleView(
        schedule=schedule,
        event=db.get_one(EventoVisibleDB, schedule.event_id),
        generated_by=db.get_one(User, schedule.generated_by_id).name,
    )


def _audit_values(schedule: WaveSchedule) -> dict[str, Any]:
    return {
        "segmentation_id": schedule.segmentation_id,
        "opening_at": asegurar_utc(schedule.opening_at).isoformat(),
        "closing_at": asegurar_utc(schedule.closing_at).isoformat(),
    }


def get_schedule(db: Session, club_id: uuid.UUID, event_id: str) -> ScheduleView:
    schedule = db.scalar(
        select(WaveSchedule).where(
            WaveSchedule.event_id == event_id,
            WaveSchedule.club_id == club_id,
        )
    )
    if schedule is None:
        raise error(
            status.HTTP_404_NOT_FOUND,
            "SCHEDULE_NOT_FOUND",
            "Este partido todavía no tiene cronograma.",
        )
    return _view(db, schedule)


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
    return _view(db, schedule)

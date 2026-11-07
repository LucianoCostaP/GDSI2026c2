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
from ..core.date_utils import asegurar_utc
from ..models import (
    EventoVisibleDB,
    User,
    WaveSchedule,
    WaveScheduleStatus,
    WaveSegmentation,
    utcnow,
)
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
    event = segmentation_service.upcoming_partido(
        db,
        club_id,
        event_id,
        _now(now),
        action="armar el cronograma",
        started="no se puede generar el cronograma",
    )
    segmentation = _segmentation_required(db, event)

    schedule = WaveSchedule(
        club_id=club_id,
        event_id=event.id_interno,
        segmentation_id=segmentation.id,
        opening_at=asegurar_utc(opening_at),
        closing_at=asegurar_utc(closing_at),
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

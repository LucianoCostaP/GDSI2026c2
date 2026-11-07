"""Cronograma de habilitación de las olas de un Partido (HU-37).

El club sale siempre de la cuenta del Admin (decisión 34): estos endpoints no leen `club_id`.
La hora es siempre la del servidor.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from ..auth import CurrentAdmin, CurrentAdminClub
from ..config import settings
from ..core.date_utils import asegurar_utc
from ..db import get_db
from ..schemas.segmentation import SegmentationEventOut
from ..schemas.wave_schedule import (
    GenerateScheduleIn,
    ScheduledWaveOut,
    WaveScheduleOut,
)
from ..scoring.wave_schedule import step_seconds
from ..services import wave_schedule_service

router = APIRouter(tags=["admin wave schedule"])

Db = Annotated[Session, Depends(get_db)]


def _schedule_out(view: wave_schedule_service.ScheduleView) -> WaveScheduleOut:
    schedule = view.schedule
    return WaveScheduleOut(
        event=SegmentationEventOut(
            id_interno=view.event.id_interno,
            titulo=view.event.titulo,
            fecha_hora=view.event.fecha_hora,
            lugar=view.event.lugar,
        ),
        status=schedule.status,
        opening_at=schedule.opening_at,
        closing_at=schedule.closing_at,
        step_seconds=step_seconds(
            asegurar_utc(schedule.opening_at),
            asegurar_utc(schedule.closing_at),
            len(view.waves),
        ),
        min_step_minutes=settings.wave_min_step_minutes,
        locked=view.locked,
        generated_at=schedule.generated_at,
        generated_by=view.generated_by,
        confirmed_at=schedule.confirmed_at,
        confirmed_by=view.confirmed_by,
        waves=[
            ScheduledWaveOut(
                order=item.wave.order,
                percentile_from=item.wave.percentile_from,
                percentile_to=item.wave.percentile_to,
                position_from=item.wave.position_from,
                position_to=item.wave.position_to,
                socios=item.wave.socios,
                starts_at=item.starts_at,
                state=state,
            )
            for item, state in zip(view.waves, view.states, strict=True)
        ],
    )


@router.get("/admin/events/{event_id}/schedule")
def get_schedule(event_id: str, club_id: CurrentAdminClub, db: Db) -> WaveScheduleOut:
    return _schedule_out(wave_schedule_service.get_schedule(db, club_id, event_id))


@router.post("/admin/events/{event_id}/schedule", status_code=status.HTTP_201_CREATED)
def generate_schedule(
    event_id: str,
    body: GenerateScheduleIn,
    response: Response,
    admin: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Db,
) -> WaveScheduleOut:
    """Genera el cronograma en borrador: `201` la primera vez; `200` cuando reemplaza uno
    anterior (con `confirmed`)."""
    view, replaced = wave_schedule_service.generate(
        db,
        admin,
        club_id,
        event_id,
        opening_at=body.opening_at,
        closing_at=body.closing_at,
        confirmed=body.confirmed,
    )
    if replaced:
        response.status_code = status.HTTP_200_OK
    return _schedule_out(view)


@router.post("/admin/events/{event_id}/schedule/confirm")
def confirm_schedule(
    event_id: str, admin: CurrentAdmin, club_id: CurrentAdminClub, db: Db
) -> WaveScheduleOut:
    """Confirma el borrador: desde ahí lo ven los socios."""
    return _schedule_out(wave_schedule_service.confirm(db, admin, club_id, event_id))

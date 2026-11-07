"""Cronograma de habilitación de las olas de un Partido (HU-37).

El club sale siempre de la cuenta del Admin (decisión 34): estos endpoints no leen `club_id`.
La hora es siempre la del servidor.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..auth import CurrentAdmin, CurrentAdminClub
from ..db import get_db
from ..schemas.segmentation import SegmentationEventOut
from ..schemas.wave_schedule import GenerateScheduleIn, WaveScheduleOut
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
        generated_at=schedule.generated_at,
        generated_by=view.generated_by,
    )


@router.get("/admin/events/{event_id}/schedule")
def get_schedule(event_id: str, club_id: CurrentAdminClub, db: Db) -> WaveScheduleOut:
    return _schedule_out(wave_schedule_service.get_schedule(db, club_id, event_id))


@router.post("/admin/events/{event_id}/schedule", status_code=status.HTTP_201_CREATED)
def generate_schedule(
    event_id: str,
    body: GenerateScheduleIn,
    admin: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Db,
) -> WaveScheduleOut:
    """Genera el cronograma del Partido en borrador."""
    return _schedule_out(
        wave_schedule_service.generate(
            db,
            admin,
            club_id,
            event_id,
            opening_at=body.opening_at,
            closing_at=body.closing_at,
        )
    )

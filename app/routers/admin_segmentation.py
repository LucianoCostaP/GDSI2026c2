"""Segmentación de socios en olas de un Partido (HU-36).

El club sale siempre de la cuenta del Admin (decisión 34): estos endpoints no leen `club_id`.
La hora es siempre la del servidor.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from ..auth import CurrentAdmin, CurrentAdminClub
from ..db import get_db
from ..models import EventoVisibleDB
from ..schemas.ranking import PreflightWarningOut
from ..schemas.segmentation import (
    GenerateSegmentationIn,
    ScheduleSummaryOut,
    SegmentableEventOut,
    SegmentationEventOut,
    SegmentationOut,
    SegmentationPreflightOut,
    SegmentationRankingOut,
    SegmentationSummaryOut,
    WaveOut,
)
from ..scoring.waves import build_waves
from ..services import segmentation_service

router = APIRouter(tags=["admin segmentation"])

Db = Annotated[Session, Depends(get_db)]


def _event_out(event: EventoVisibleDB) -> SegmentationEventOut:
    return SegmentationEventOut(
        id_interno=event.id_interno,
        titulo=event.titulo,
        fecha_hora=event.fecha_hora,
        lugar=event.lugar,
    )


def _segmentation_out(view: segmentation_service.SegmentationView) -> SegmentationOut:
    segmentation = view.segmentation
    return SegmentationOut(
        event=_event_out(view.event),
        ranking=SegmentationRankingOut(
            id=view.ranking.id,
            completed_at=view.ranking.completed_at,
            rules_version=view.rules_version,
        ),
        ranked_total=segmentation.ranked_total,
        percentile_step=segmentation.percentile_step,
        generated_at=segmentation.generated_at,
        generated_by=view.generated_by,
        waves=[
            WaveOut(
                order=w.order,
                percentile_from=w.percentile_from,
                percentile_to=w.percentile_to,
                position_from=w.position_from,
                position_to=w.position_to,
                socios=w.socios,
            )
            for w in view.waves
        ],
    )


@router.get("/admin/segmentation/events")
def segmentable_events(club_id: CurrentAdminClub, db: Db) -> list[SegmentableEventOut]:
    """Partidos publicados que todavía no empezaron, con sus olas si ya se generaron."""
    return [
        SegmentableEventOut(
            event=_event_out(item.event),
            segmentation=(
                SegmentationSummaryOut(
                    generated_at=item.segmentation.generated_at,
                    waves_count=len(
                        build_waves(
                            item.segmentation.ranked_total,
                            item.segmentation.percentile_step,
                        )
                    ),
                )
                if item.segmentation
                else None
            ),
            schedule=(
                ScheduleSummaryOut(
                    status=item.schedule.status,
                    opening_at=item.schedule.opening_at,
                    closing_at=item.schedule.closing_at,
                )
                if item.schedule
                else None
            ),
        )
        for item in segmentation_service.list_segmentable_events(db, club_id)
    ]


@router.get("/admin/segmentation/preflight")
def segmentation_preflight(
    club_id: CurrentAdminClub, db: Db
) -> SegmentationPreflightOut:
    """Advertencias antes de generar (padrón viejo, cargas posteriores al ranking)."""
    return SegmentationPreflightOut(
        warnings=[
            PreflightWarningOut(code=w.code, message=w.message, data_as_of=w.data_as_of)
            for w in segmentation_service.build_preflight(db, club_id)
        ]
    )


@router.get("/admin/events/{event_id}/segmentation")
def get_segmentation(
    event_id: str, club_id: CurrentAdminClub, db: Db
) -> SegmentationOut:
    return _segmentation_out(
        segmentation_service.get_segmentation(db, club_id, event_id)
    )


@router.post(
    "/admin/events/{event_id}/segmentation", status_code=status.HTTP_201_CREATED
)
def generate_segmentation(
    event_id: str,
    body: GenerateSegmentationIn,
    response: Response,
    admin: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Db,
) -> SegmentationOut:
    """`201` la primera vez; `200` cuando reemplaza olas anteriores (con `confirmed`)."""
    view, replaced = segmentation_service.generate(
        db, admin, club_id, event_id, confirmed=body.confirmed
    )
    if replaced:
        response.status_code = status.HTTP_200_OK
    return _segmentation_out(view)

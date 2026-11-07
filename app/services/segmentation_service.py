"""Segmentación de socios en olas de un Partido (HU-36).

El servicio recibe `now` solo para los tests; si no llega, manda el reloj del servidor.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..core.date_utils import asegurar_utc
from ..models import (
    Club,
    EventoPendienteDB,
    EventoVisibleDB,
    Ranking,
    RankingEntry,
    RulesVersion,
    TipoEvento,
    User,
    WaveSegmentation,
    utcnow,
)
from ..scoring.waves import Wave, build_waves
from . import ranking_preflight_service
from .formula_service import error
from .ranking_preflight_service import PreflightWarning
from .ranking_service import get_ranking_in_force

PARTIDO = TipoEvento.PARTIDO.value


@dataclass(frozen=True)
class SegmentationView:
    segmentation: WaveSegmentation
    event: EventoVisibleDB
    ranking: Ranking
    rules_version: int
    generated_by: str
    waves: list[Wave]


@dataclass(frozen=True)
class SegmentableEvent:
    event: EventoVisibleDB
    segmentation: WaveSegmentation | None


def first_wave_opened(segmentation: WaveSegmentation) -> bool:
    """Si la primera ola ya abrió. Sin cronograma (HU-37) ninguna ola abre todavía."""
    return False


def _now(now: datetime | None) -> datetime:
    return asegurar_utc(now or utcnow())


def _segmentation_of(db: Session, event_id: str) -> WaveSegmentation | None:
    return db.scalar(
        select(WaveSegmentation).where(WaveSegmentation.event_id == event_id)
    )


def _view(db: Session, segmentation: WaveSegmentation) -> SegmentationView:
    ranking = db.get_one(Ranking, segmentation.ranking_id)
    return SegmentationView(
        segmentation=segmentation,
        event=db.get_one(EventoVisibleDB, segmentation.event_id),
        ranking=ranking,
        rules_version=db.get_one(RulesVersion, ranking.rules_version_id).number,
        generated_by=db.get_one(User, segmentation.generated_by_id).name,
        waves=build_waves(segmentation.ranked_total, segmentation.percentile_step),
    )


def list_segmentable_events(
    db: Session, club_id: uuid.UUID, now: datetime | None = None
) -> list[SegmentableEvent]:
    """Los Partidos publicados del club que todavía no empezaron, con su segmentación."""
    rows = db.execute(
        select(EventoVisibleDB, WaveSegmentation)
        .outerjoin(
            WaveSegmentation, WaveSegmentation.event_id == EventoVisibleDB.id_interno
        )
        .where(
            EventoVisibleDB.club_id == club_id,
            EventoVisibleDB.tipo == PARTIDO,
            EventoVisibleDB.fecha_hora > _now(now),
        )
        .order_by(EventoVisibleDB.fecha_hora, EventoVisibleDB.id_interno)
    ).all()
    return [SegmentableEvent(event, segmentation) for event, segmentation in rows]


def build_preflight(
    db: Session, club_id: uuid.UUID, now: datetime | None = None
) -> list[PreflightWarning]:
    """Advertencias antes de segmentar (escenario 10). No bloquean."""
    club = db.get_one(Club, club_id)
    candidates = (
        ranking_preflight_service.roster_warning(db, club, _now(now)),
        ranking_preflight_service.loads_after_ranking_warning(db, club),
    )
    return [warning for warning in candidates if warning is not None]


def get_segmentation(
    db: Session, club_id: uuid.UUID, event_id: str
) -> SegmentationView:
    segmentation = db.scalar(
        select(WaveSegmentation).where(
            WaveSegmentation.event_id == event_id,
            WaveSegmentation.club_id == club_id,
        )
    )
    if segmentation is None:
        raise error(
            status.HTTP_404_NOT_FOUND,
            "SEGMENTATION_NOT_FOUND",
            "Este partido todavía no tiene olas generadas.",
        )
    return _view(db, segmentation)


def upcoming_partido(
    db: Session,
    club_id: uuid.UUID,
    event_id: str,
    now: datetime,
    *,
    action: str = "generar las olas",
    started: str = "no se pueden generar olas",
) -> EventoVisibleDB:
    """El Partido publicado y no empezado del club (HU-36 escenario 6, HU-37). Lo bloquea
    mientras se genera, para que dos pedidos simultáneos no se pisen.

    `action` y `started` adaptan los mensajes a quien lo usa (olas o cronograma)."""
    event = db.scalar(
        select(EventoVisibleDB)
        .where(
            EventoVisibleDB.id_interno == event_id,
            EventoVisibleDB.club_id == club_id,
        )
        .with_for_update()
    )
    if event is None:
        pending = db.scalar(
            select(EventoPendienteDB.id_interno).where(
                EventoPendienteDB.id_interno == event_id,
                EventoPendienteDB.club_id == club_id,
            )
        )
        if pending is not None:
            raise error(
                status.HTTP_409_CONFLICT,
                "EVENT_NOT_PUBLISHED",
                f"El evento todavía no está publicado: publicalo antes de {action}.",
            )
        raise error(
            status.HTTP_404_NOT_FOUND,
            "EVENT_NOT_FOUND",
            "No encontramos el evento.",
        )
    if event.tipo != PARTIDO:
        raise error(
            status.HTTP_409_CONFLICT,
            "NOT_A_PARTIDO",
            "Las olas son solo para partidos: este evento no es un partido.",
        )
    if asegurar_utc(event.fecha_hora) <= now:
        raise error(
            status.HTTP_409_CONFLICT,
            "EVENT_ALREADY_STARTED",
            f"El partido ya empezó: {started}.",
        )
    return event


def _ranking_to_use(db: Session, club_id: uuid.UUID) -> tuple[Ranking, int]:
    ranking = get_ranking_in_force(db, club_id)
    if ranking is None:
        raise error(
            status.HTTP_409_CONFLICT,
            "NO_COMPLETED_RANKING",
            "Todavía no hay un ranking calculado: calculalo antes de generar las olas.",
        )
    ranked_total = db.scalar(
        select(func.count())
        .select_from(RankingEntry)
        .where(RankingEntry.ranking_id == ranking.id)
    )
    if not ranked_total:
        raise error(
            status.HTTP_409_CONFLICT,
            "RANKING_WITHOUT_SOCIOS",
            "El ranking vigente no tiene socios: no hay a quién asignar a las olas.",
        )
    return ranking, ranked_total


def generate(
    db: Session,
    admin: User,
    club_id: uuid.UUID,
    event_id: str,
    *,
    confirmed: bool,
    now: datetime | None = None,
) -> tuple[SegmentationView, bool]:
    """Genera o regenera las olas del Partido. Devuelve la vista y si reemplazó una anterior."""
    event = upcoming_partido(db, club_id, event_id, _now(now))
    ranking, ranked_total = _ranking_to_use(db, club_id)

    segmentation = _segmentation_of(db, event.id_interno)
    previous = None
    if segmentation is not None:
        if first_wave_opened(segmentation):
            raise error(
                status.HTTP_409_CONFLICT,
                "SEGMENTATION_LOCKED",
                "La primera ola ya abrió: no se pueden regenerar las olas.",
            )
        if not confirmed:
            raise error(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "CONFIRMATION_REQUIRED",
                "Este partido ya tiene olas. Confirmá para reemplazarlas.",
            )
        previous = {
            "ranking_id": segmentation.ranking_id,
            "ranked_total": segmentation.ranked_total,
            "percentile_step": segmentation.percentile_step,
        }
    values = {
        "ranking_id": ranking.id,
        "ranked_total": ranked_total,
        "percentile_step": settings.wave_percentile_step,
        "generated_at": utcnow(),
        "generated_by_id": admin.id,
    }
    if segmentation is None:
        segmentation = WaveSegmentation(
            club_id=club_id, event_id=event.id_interno, **values
        )
        db.add(segmentation)
    else:
        for field, value in values.items():
            setattr(segmentation, field, value)
    db.flush()

    audit.record(
        db,
        "wave_segmentation.regenerated" if previous else "wave_segmentation.generated",
        actor_id=admin.id,
        entity="wave_segmentation",
        entity_id=segmentation.id,
        event_id=event.id_interno,
        previous=previous,
        new={
            "ranking_id": ranking.id,
            "ranked_total": ranked_total,
            "percentile_step": segmentation.percentile_step,
        },
    )
    db.commit()
    return _view(db, segmentation), previous is not None

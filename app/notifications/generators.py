"""Generadores de las notificaciones del catálogo (HU-19 user story 3, notificaciones §2 y §4).

Cada generador arma los destinatarios, la referencia y los parámetros del texto, y llama a
`notify`. Ninguno le tira un error a quien lo llama: el proceso que lo dispara (la publicación,
el ranking, el trabajo de olas) sigue igual aunque la notificación falle.
"""

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..core.date_utils import a_hora_buenos_aires, asegurar_utc
from ..models import (
    EventoVisibleDB,
    Member,
    Ranking,
    RankingEntry,
    RankingState,
    Role,
    Socio,
    User,
    WaveSchedule,
    WaveScheduleStatus,
    WaveSegmentation,
)
from ..models.auth import utcnow
from ..scoring.wave_schedule import WaveState, schedule_waves, wave_state
from ..scoring.waves import build_waves
from .notify import notify

logger = logging.getLogger(__name__)


def _when(moment: datetime) -> dict[str, str]:
    """`{fecha}` y `{hora}` del texto, en hora de Buenos Aires (notificaciones §2)."""
    local = a_hora_buenos_aires(moment)
    return {"fecha": local.strftime("%d/%m/%Y"), "hora": local.strftime("%H:%M")}


def _club_members(db: Session, club_id: uuid.UUID) -> list[int]:
    """Las cuentas de socio activadas del club (la cuenta existe solo desde la activación),
    salvo las de un socio dado de baja en el padrón al momento de generar (escenario 9)."""
    dado_de_baja = (
        select(Socio.id)
        .join(Member, Member.dni == Socio.dni)
        .where(
            Member.member_id == User.member_id,
            Socio.club_id == club_id,
            Socio.activo.is_(False),
        )
        .exists()
    )
    return list(
        db.scalars(
            select(User.id).where(
                User.role == Role.MEMBER, User.club_id == club_id, ~dado_de_baja
            )
        )
    )


def event_published(db: Session, event_id: str, *, now: datetime | None = None) -> int:
    """`event_published` para todos los socios activados del club del evento (escenario 1).

    Se llama al final de la publicación de HU-22, manual o automática, después del commit.
    Devuelve cuántas notificaciones creó.
    """
    try:
        event = db.get(EventoVisibleDB, event_id)
        if event is None:
            logger.warning(
                "event_published: no existe el evento publicado %s", event_id
            )
            return 0
        recipients = _club_members(db, event.club_id)
    except Exception:
        db.rollback()
        logger.exception("event_published: no se pudieron leer los destinatarios")
        return 0
    return notify(
        db,
        "event_published",
        f"event:{event.id_interno}:published",
        recipients,
        club_id=event.club_id,
        reference={"event_id": event.id_interno},
        params={"titulo": event.titulo, **_when(event.fecha_hora)},
        now=now,
    )


def _ranked_members(
    db: Session,
    ranking_id: int,
    club_id: uuid.UUID,
    positions: tuple[int, int] | None = None,
) -> list[int]:
    """Las cuentas activadas de los socios con entrada en el ranking (opcionalmente, entre dos
    posiciones) que no están dados de baja al momento de generar (escenario 9). Del socio del
    padrón a su cuenta por club y documento, como `socio_of`."""
    query = (
        select(User.id)
        .join(Member, Member.member_id == User.member_id)
        .join(Socio, (Socio.dni == Member.dni) & (Socio.club_id == club_id))
        .join(RankingEntry, RankingEntry.socio_id == Socio.id)
        .where(
            RankingEntry.ranking_id == ranking_id,
            Socio.activo.is_(True),
            User.role == Role.MEMBER,
            User.club_id == club_id,
        )
    )
    if positions is not None:
        query = query.where(RankingEntry.position.between(*positions))
    return list(db.scalars(query))


def ranking_completed(db: Session, ranking_id: int) -> int:
    """`ranking_completed` para los socios activados con entrada en el ranking (escenario 5).

    Se llama cuando la corrida de HU-25 queda `completed`, después del commit; una corrida
    `failed` no llega acá (escenario 6). Devuelve cuántas notificaciones creó.
    """
    try:
        ranking = db.get(Ranking, ranking_id)
        if ranking is None or ranking.status != RankingState.COMPLETED:
            logger.warning(
                "ranking_completed: el ranking %s no está completado", ranking_id
            )
            return 0
        recipients = _ranked_members(db, ranking.id, ranking.club_id)
        club_id, completed_at = ranking.club_id, ranking.completed_at
    except Exception:
        db.rollback()
        logger.exception("ranking_completed: no se pudieron leer los destinatarios")
        return 0
    return notify(
        db,
        "ranking_completed",
        f"ranking:{ranking_id}",
        recipients,
        club_id=club_id,
        reference={"ranking_id": ranking_id},
        params={},
        now=completed_at,
    )


def open_waves(
    db: Session, *, now: datetime | None = None, club_id: uuid.UUID | None = None
) -> int:
    """Trabajo periódico de apertura de olas (escenarios 2 a 4, notificaciones §4).

    Lee los cronogramas `confirmed` (sin cambiarlos; `draft` e `invalidated` no generan nada)
    y, para cada ola cuya hora de inicio llegó y cuyo cierre general no pasó, avisa
    `wave_opened` a los socios de esa ola. Una ola que abrió hace más que
    `wave_notification_catchup_minutes` se saltea y se registra. Es idempotente: correrlo de
    nuevo no duplica. Con `club_id`, solo los cronogramas de ese club. Devuelve cuántas
    notificaciones creó.
    """
    now = asegurar_utc(now or utcnow())
    query = select(WaveSchedule.id).where(
        WaveSchedule.status == WaveScheduleStatus.CONFIRMED
    )
    if club_id is not None:
        query = query.where(WaveSchedule.club_id == club_id)
    try:
        schedule_ids = list(db.scalars(query))
    except Exception:
        db.rollback()
        logger.exception("open_waves: no se pudieron leer los cronogramas")
        return 0
    return sum(
        _open_schedule_waves(db, schedule_id, now) for schedule_id in schedule_ids
    )


def _open_schedule_waves(db: Session, schedule_id: int, now: datetime) -> int:
    catchup = timedelta(minutes=settings.wave_notification_catchup_minutes)
    try:
        schedule = db.get_one(WaveSchedule, schedule_id)
        segmentation = db.get_one(WaveSegmentation, schedule.segmentation_id)
        event = db.get_one(EventoVisibleDB, schedule.event_id)
        closing = asegurar_utc(schedule.closing_at)
        waves = schedule_waves(
            build_waves(segmentation.ranked_total, segmentation.percentile_step),
            asegurar_utc(schedule.opening_at),
            closing,
        )
        opened: list[tuple[int, list[int]]] = []
        for scheduled in waves:
            if wave_state(scheduled.starts_at, closing, now) != WaveState.OPEN:
                continue
            if now - scheduled.starts_at > catchup:
                logger.info(
                    "open_waves: se saltea la ola %s del evento %s (cronograma %s): abrió "
                    "hace más de %s minutos",
                    scheduled.wave.order,
                    event.id_interno,
                    schedule_id,
                    settings.wave_notification_catchup_minutes,
                )
                continue
            wave = scheduled.wave
            opened.append(
                (
                    wave.order,
                    _ranked_members(
                        db,
                        segmentation.ranking_id,
                        segmentation.club_id,
                        (wave.position_from, wave.position_to),
                    ),
                )
            )
        # Lo que se lee de la base se suelta antes de notificar, que confirma o deshace.
        event_id, titulo, club_id = event.id_interno, event.titulo, event.club_id
    except Exception:
        db.rollback()
        logger.exception("open_waves: falló el cronograma %s", schedule_id)
        return 0
    return sum(
        notify(
            db,
            "wave_opened",
            f"event:{event_id}:wave:{order}:schedule:{schedule_id}",
            recipients,
            club_id=club_id,
            reference={"event_id": event_id},
            # La fecha del texto es el cierre general del cronograma (notificaciones §2).
            params={"titulo": titulo, **_when(closing)},
            now=now,
        )
        for order, recipients in opened
    )

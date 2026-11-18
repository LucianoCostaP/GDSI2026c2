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
from ..scoring.wave_schedule import (
    ScheduledWave,
    WaveState,
    schedule_waves,
    wave_state,
)
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


def club_member_ids(db: Session, club_id: uuid.UUID) -> list[int]:
    """Los destinatarios de una notificación de evento del club (para contarlos antes de
    generarla, como la vista previa de una reprogramación de HU-23B)."""
    return _club_members(db, club_id)


def _event_to_club(
    db: Session,
    type: str,
    event_id: str,
    occurrence: str,
    *,
    params: dict[str, str] | None = None,
    now: datetime | None = None,
) -> int:
    """`type` sobre el evento `event_id` para todos los socios activados de su club, con la
    clave `event:{event_id}:{occurrence}`. Lee el evento ya confirmado, así que el texto lleva
    su título, fecha y hora vigentes."""
    try:
        event = db.get(EventoVisibleDB, event_id)
        if event is None:
            logger.warning("%s: no existe el evento publicado %s", type, event_id)
            return 0
        recipients = _club_members(db, event.club_id)
        club_id, titulo, when = event.club_id, event.titulo, _when(event.fecha_hora)
    except Exception:
        db.rollback()
        logger.exception("%s: no se pudieron leer los destinatarios", type)
        return 0
    return notify(
        db,
        type,
        f"event:{event_id}:{occurrence}",
        recipients,
        club_id=club_id,
        reference={"event_id": event_id},
        params={"titulo": titulo, **when, **(params or {})},
        now=now,
    )


def event_published(db: Session, event_id: str, *, now: datetime | None = None) -> int:
    """`event_published` para todos los socios activados del club del evento (escenario 1).

    Se llama al final de la publicación de HU-22, manual o automática, después del commit.
    Devuelve cuántas notificaciones creó.
    """
    return _event_to_club(db, "event_published", event_id, "published", now=now)


def event_rescheduled(
    db: Session, event_id: str, reprogramming_id: str, *, now: datetime | None = None
) -> int:
    """`event_rescheduled` para todos los socios activados del club cuando el Admin reprograma
    un evento publicado (HU-23B US2 escenario 10, US4 escenario 1; clave
    `event:{event_id}:rescheduled:{reprogramming_id}`). El texto lleva la fecha y la hora
    nuevas. Se llama después del commit, que nunca se deshace por esto. El código viejo de
    HU-23 lo llama con el id del cambio aprobado."""
    return _event_to_club(
        db, "event_rescheduled", event_id, f"rescheduled:{reprogramming_id}", now=now
    )


def event_withdrawn(
    db: Session, event_id: str, motivo: str, withdrawn_at: datetime
) -> int:
    """`event_withdrawn` cuando el Admin retira un evento publicado (HU-23). Un evento se puede
    retirar y restaurar más de una vez: cada retiro es una ocurrencia, por su momento."""
    return _event_to_club(
        db,
        "event_withdrawn",
        event_id,
        f"withdrawn:{asegurar_utc(withdrawn_at).isoformat()}",
        params={"motivo": motivo},
        now=withdrawn_at,
    )


def event_restored(db: Session, event_id: str, restored_at: datetime) -> int:
    """`event_restored` cuando el Admin restaura un evento retirado (HU-23), una ocurrencia
    por restauración."""
    return _event_to_club(
        db,
        "event_restored",
        event_id,
        f"restored:{asegurar_utc(restored_at).isoformat()}",
        now=restored_at,
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


def ranked_member_ids(
    db: Session, ranking_id: int, club_id: uuid.UUID, positions: tuple[int, int]
) -> list[int]:
    """Los destinatarios de un aviso de turno entre dos posiciones del ranking (para contarlos
    antes de generarlo, como la vista previa de una reprogramación de HU-23B)."""
    return _ranked_members(db, ranking_id, club_id, positions)


def waves_moved(
    db: Session,
    event_id: str,
    reprogramming_id: str,
    *,
    schedule_id: int,
    joined_order: int,
    first_moved_order: int,
    joined_open: bool,
    now: datetime | None = None,
) -> int:
    """El aviso a los socios de las olas que una reprogramación sumó a la ola `joined_order`
    (HU-23B US4, escenarios 2 y 3). Se llama después del commit, con el cronograma ya ajustado.

    Si la ola a la que se sumaron todavía no abrió, `wave_rescheduled` con su hora de inicio
    (clave `event:{event_id}:wave-moved:{reprogramming_id}`); el trabajo de olas les avisa
    `wave_opened` cuando llegue. Si ya abrió, `wave_opened` en el momento, con el cierre
    nuevo y la misma clave del trabajo, que así no lo repite. Devuelve cuántas creó.
    """
    try:
        schedule = db.get_one(WaveSchedule, schedule_id)
        segmentation = db.get_one(WaveSegmentation, schedule.segmentation_id)
        event = db.get_one(EventoVisibleDB, event_id)
        waves = schedule_waves(
            build_waves(segmentation.ranked_total, segmentation.percentile_step),
            asegurar_utc(schedule.opening_at),
            asegurar_utc(schedule.closing_at),
            schedule.merged_into_order,
        )
        # Las olas movidas son las últimas: de `first_moved_order` a la N.
        recipients = _ranked_members(
            db,
            segmentation.ranking_id,
            segmentation.club_id,
            (
                waves[first_moved_order - 1].wave.position_from,
                waves[-1].wave.position_to,
            ),
        )
        joined_starts_at = waves[joined_order - 1].starts_at
        closing = asegurar_utc(schedule.effective_closing)
        titulo, club_id = event.titulo, event.club_id
    except Exception:
        db.rollback()
        logger.exception("waves_moved: no se pudieron leer los destinatarios")
        return 0
    if joined_open:
        return notify(
            db,
            "wave_opened",
            f"event:{event_id}:wave:{joined_order}:schedule:{schedule_id}",
            recipients,
            club_id=club_id,
            reference={"event_id": event_id},
            params={"titulo": titulo, **_when(closing)},
            now=now,
        )
    return notify(
        db,
        "wave_rescheduled",
        f"event:{event_id}:wave-moved:{reprogramming_id}",
        recipients,
        club_id=club_id,
        reference={"event_id": event_id},
        params={"titulo": titulo, **_when(joined_starts_at)},
        now=now,
    )


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


def _wave_groups(
    waves: list[ScheduledWave], merged_into_order: int | None
) -> list[tuple[int, datetime, tuple[int, int]]]:
    """Las olas que abren por separado: orden, hora de inicio y posiciones del ranking. Con
    una fusión, la ola k incluye las posiciones de las olas k+1 a N (HU-23B US3)."""
    groups: list[tuple[int, datetime, tuple[int, int]]] = []
    for scheduled in waves:
        wave = scheduled.wave
        if merged_into_order is not None and wave.order > merged_into_order:
            order, starts_at, (first, _) = groups[-1]
            groups[-1] = (order, starts_at, (first, wave.position_to))
        else:
            groups.append(
                (
                    wave.order,
                    scheduled.starts_at,
                    (wave.position_from, wave.position_to),
                )
            )
    return groups


def _open_schedule_waves(db: Session, schedule_id: int, now: datetime) -> int:
    catchup = timedelta(minutes=settings.wave_notification_catchup_minutes)
    try:
        schedule = db.get_one(WaveSchedule, schedule_id)
        segmentation = db.get_one(WaveSegmentation, schedule.segmentation_id)
        event = db.get_one(EventoVisibleDB, schedule.event_id)
        # Abre hasta el cierre efectivo, y las olas fusionadas por una reprogramación (HU-23B)
        # abren con la ola a la que se sumaron, con su misma clave.
        closing = asegurar_utc(schedule.effective_closing)
        waves = schedule_waves(
            build_waves(segmentation.ranked_total, segmentation.percentile_step),
            asegurar_utc(schedule.opening_at),
            asegurar_utc(schedule.closing_at),
            schedule.merged_into_order,
        )
        opened: list[tuple[int, list[int]]] = []
        for order, starts_at, positions in _wave_groups(
            waves, schedule.merged_into_order
        ):
            if wave_state(starts_at, closing, now) != WaveState.OPEN:
                continue
            if now - starts_at > catchup:
                logger.info(
                    "open_waves: se saltea la ola %s del evento %s (cronograma %s): abrió "
                    "hace más de %s minutos",
                    order,
                    event.id_interno,
                    schedule_id,
                    settings.wave_notification_catchup_minutes,
                )
                continue
            opened.append(
                (
                    order,
                    _ranked_members(
                        db, segmentation.ranking_id, segmentation.club_id, positions
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

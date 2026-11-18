"""Eventos publicados que el Admin puede reprogramar o retirar (HU-23B).

El club sale siempre de la cuenta del Admin (decisión 34). El servicio recibe `now` solo
para los tests; si no llega, manda el reloj del servidor.
"""

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..config import settings
from ..core.date_utils import BUENOS_AIRES_TZ, asegurar_utc
from ..models import (
    EventoPendienteDB,
    EventoVisibleDB,
    EventReprogramming,
    TipoEvento,
    User,
    WaveSchedule,
    WaveScheduleStatus,
    WaveSegmentation,
    utcnow,
)
from ..notifications.generators import club_member_ids
from ..scoring.wave_schedule import (
    RescheduleImpact,
    ScheduleEffect,
    effective_wave_starts,
    reschedule_impact,
)
from ..scoring.waves import Wave, build_waves
from .formula_service import error

# Estado de un evento publicado en `eventos_visibles`; el retirado es `withdrawn`.
PUBLICADO = "publicado"
TIPOS_PUBLICABLES = (TipoEvento.PARTIDO.value, TipoEvento.INSTITUCIONAL.value)


@dataclass(frozen=True)
class PublishedEvent:
    event: EventoVisibleDB
    # Cronograma de las olas (HU-37), solo para Partidos que ya tienen uno.
    schedule: WaveSchedule | None


def list_upcoming(
    db: Session, club_id: uuid.UUID, now: datetime | None = None
) -> list[PublishedEvent]:
    """Los eventos publicados del club que todavía no empezaron, el más cercano primero
    (US1, escenarios 1 y 3). Un evento retirado, histórico o de otro club no aparece; los
    pendientes y descartados viven en otra tabla (HU-21)."""
    rows = db.execute(
        select(EventoVisibleDB, WaveSchedule)
        .outerjoin(WaveSchedule, WaveSchedule.event_id == EventoVisibleDB.id_interno)
        .where(
            EventoVisibleDB.club_id == club_id,
            EventoVisibleDB.estado == PUBLICADO,
            EventoVisibleDB.tipo.in_(TIPOS_PUBLICABLES),
            EventoVisibleDB.fecha_hora > (now or utcnow()),
        )
        .order_by(EventoVisibleDB.fecha_hora, EventoVisibleDB.id_interno)
    ).all()
    return [PublishedEvent(event, schedule) for event, schedule in rows]


def _find_schedule(db: Session, event_id: str) -> WaveSchedule | None:
    return db.scalar(select(WaveSchedule).where(WaveSchedule.event_id == event_id))


def _listed_event(
    db: Session,
    club_id: uuid.UUID,
    event_id: str,
    now: datetime,
    *,
    for_update: bool = True,
) -> EventoVisibleDB:
    """El evento sobre el que actúa el Admin, si está en su listado (US1); si no, el error
    que corresponde. Uno de otro club, retirado o histórico responde como desconocido.
    Para aplicar una acción se bloquea la fila, así dos Admins no la cambian a la vez."""
    query = select(EventoVisibleDB).where(
        EventoVisibleDB.id_interno == event_id,
        EventoVisibleDB.club_id == club_id,
    )
    event = db.scalar(query.with_for_update() if for_update else query)
    if (
        event is None
        or event.tipo not in TIPOS_PUBLICABLES
        or event.estado != PUBLICADO
    ):
        pending = db.scalar(
            select(EventoPendienteDB.id_interno).where(
                EventoPendienteDB.id_interno == event_id,
                EventoPendienteDB.club_id == club_id,
            )
        )
        if event is None and pending is not None:
            raise error(
                status.HTTP_409_CONFLICT,
                "EVENT_NOT_PUBLISHED",
                "El evento no está publicado.",
            )
        raise error(
            status.HTTP_404_NOT_FOUND, "EVENT_NOT_FOUND", "No encontramos el evento."
        )
    if asegurar_utc(event.fecha_hora) <= now:
        raise error(
            status.HTTP_409_CONFLICT,
            "EVENT_ALREADY_STARTED",
            "El evento ya empezó: no se puede reprogramar ni retirar.",
        )
    return event


# Fecha y hora ISO 8601 con la hora obligatoria (los segundos y la zona son opcionales).
_DATETIME = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:?\d{2})?"
)


def _parse_start(raw: str | None) -> datetime:
    """La fecha y hora pedida, en UTC (escenario 6). Sin zona horaria se lee en Buenos Aires
    (cross-cutting, sección 1)."""
    try:
        if raw is None or not _DATETIME.fullmatch(raw.strip()):
            raise ValueError(raw)
        value = datetime.fromisoformat(raw.strip())
    except ValueError:
        raise error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_DATETIME",
            "La fecha y hora no es válida: usá el formato AAAA-MM-DD HH:MM.",
        ) from None
    if value.tzinfo is None:
        value = value.replace(tzinfo=BUENOS_AIRES_TZ)
    return asegurar_utc(value)


@dataclass(frozen=True)
class ReschedulePlan:
    """Lo que hace una reprogramación (US2 escenario 7): se muestra antes de confirmar y se
    aplica tal cual."""

    event: EventoVisibleDB
    previous_start: datetime
    new_start: datetime
    schedule: WaveSchedule | None
    impact: RescheduleImpact
    # Las olas de la segmentación (HU-36), para contar los socios que se mueven.
    waves: list[Wave]
    # La hora de inicio efectiva de la ola a la que se suman las olas afectadas.
    target_starts_at: datetime | None
    # Cuántos socios reciben `event_rescheduled` (las cuentas activadas del club).
    event_rescheduled: int

    @property
    def moved_waves(self) -> list[Wave]:
        return [w for w in self.waves if w.order in self.impact.moved_orders]


@dataclass(frozen=True)
class Rescheduled:
    published: PublishedEvent
    reprogramming_id: uuid.UUID
    plan: ReschedulePlan


def _plan(
    db: Session,
    club_id: uuid.UUID,
    event_id: str,
    raw_start: str | None,
    *,
    other_fields: Iterable[str],
    now: datetime,
    expected_version: int | None = None,
    for_update: bool,
) -> ReschedulePlan:
    """Valida el pedido en el orden de la spec y calcula su efecto sobre el cronograma."""
    if any(True for _ in other_fields):
        raise error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "FIELD_NOT_EDITABLE",
            "Al reprogramar solo se puede cambiar la fecha y la hora.",
        )
    new_start = _parse_start(raw_start)
    event = _listed_event(db, club_id, event_id, now, for_update=for_update)
    # Escenario 9: otro Admin reprogramó (o retiró) el evento después de cargar el formulario.
    if expected_version is not None and expected_version != event.version:
        raise error(
            status.HTTP_409_CONFLICT,
            "EVENT_CHANGED",
            "El evento cambió mientras lo editabas. Revisá los datos actuales y volvé a "
            "intentar.",
        )
    previous_start = asegurar_utc(event.fecha_hora)
    if new_start == previous_start:
        raise error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "NO_CHANGES",
            "No hay cambios para guardar.",
        )
    if new_start <= now:
        raise error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "START_NOT_IN_FUTURE",
            "La nueva fecha y hora tiene que ser posterior a este momento.",
        )

    schedule = _find_schedule(db, event.id_interno)
    segmentation = db.scalar(
        select(WaveSegmentation).where(WaveSegmentation.event_id == event.id_interno)
    )
    waves = (
        build_waves(segmentation.ranked_total, segmentation.percentile_step)
        if segmentation is not None
        else []
    )
    impact = RescheduleImpact(ScheduleEffect.NO_SCHEDULE)
    target_starts_at = None
    if schedule is not None and waves:
        starts = effective_wave_starts(
            asegurar_utc(schedule.opening_at),
            asegurar_utc(schedule.closing_at),
            len(waves),
            schedule.merged_into_order,
        )
        impact = reschedule_impact(
            status=schedule.status.value,
            starts=starts,
            closing=asegurar_utc(schedule.effective_closing),
            merged_into_order=schedule.merged_into_order,
            new_start=new_start,
            now=now,
            min_step_minutes=settings.wave_min_step_minutes,
        )
        if impact.effect == ScheduleEffect.WAVES_MERGED:
            assert impact.merged_into_order is not None
            target_starts_at = starts[impact.merged_into_order - 1]
    return ReschedulePlan(
        event=event,
        previous_start=previous_start,
        new_start=new_start,
        schedule=schedule,
        impact=impact,
        waves=waves,
        target_starts_at=target_starts_at,
        event_rescheduled=len(club_member_ids(db, club_id)),
    )


def preview(
    db: Session,
    club_id: uuid.UUID,
    event_id: str,
    fecha_hora: str | None,
    *,
    other_fields: Iterable[str] = (),
    now: datetime | None = None,
) -> ReschedulePlan:
    """Lo que pasaría con la reprogramación, sin cambiar nada (US2 escenario 7, US3)."""
    return _plan(
        db,
        club_id,
        event_id,
        fecha_hora,
        other_fields=other_fields,
        now=asegurar_utc(now or utcnow()),
        for_update=False,
    )


def _schedule_values(schedule: WaveSchedule) -> dict[str, Any]:
    return {
        "status": schedule.status.value,
        "closing_at": asegurar_utc(schedule.effective_closing).isoformat(),
        "merged_into_order": schedule.merged_into_order,
    }


def _apply_to_schedule(db: Session, admin: User, plan: ReschedulePlan) -> None:
    """Aplica el efecto calculado al cronograma y lo audita (US3 escenario 9)."""
    schedule, impact = plan.schedule, plan.impact
    if schedule is None or impact.effect in (
        ScheduleEffect.NO_SCHEDULE,
        ScheduleEffect.NONE,
    ):
        return
    previous = _schedule_values(schedule)
    if impact.effect == ScheduleEffect.INVALIDATED:
        # Escenarios 6 y 7: la segmentación se conserva; hay que generar el cronograma de
        # nuevo (HU-37).
        schedule.status = WaveScheduleStatus.INVALIDATED
        action = "wave_schedule.invalidated"
    else:
        schedule.effective_closing_at = impact.new_closing
        schedule.merged_into_order = impact.merged_into_order
        action = "wave_schedule.adjusted"
    audit.record(
        db,
        action,
        actor_id=admin.id,
        entity="wave_schedule",
        entity_id=schedule.id,
        event_id=schedule.event_id,
        reason="event.rescheduled",
        previous=previous,
        new=_schedule_values(schedule),
        moved_waves=list(impact.moved_orders),
    )


def reschedule(
    db: Session,
    admin: User,
    club_id: uuid.UUID,
    event_id: str,
    fecha_hora: str | None,
    *,
    expected_version: int,
    expected_schedule_effect: str | None = None,
    expected_merged_into_order: int | None = None,
    other_fields: Iterable[str] = (),
    now: datetime | None = None,
) -> Rescheduled:
    """Cambia la fecha y hora de un evento publicado (US2, escenarios 2 a 9).

    El evento sigue `publicado`, con su clase o puntos y los datos del club, sin una nueva
    publicación: lo que ven los Socios (HU-17, HU-18, HU-39) lee la fecha nueva. Se suma 1 a
    la `version`, se borra la marca de cancelado por el club (edge cases), se ajusta el
    cronograma como mostró la vista previa y se audita todo en la misma transacción.

    Si llega el efecto que vio el Admin en la vista previa y ya no es el mismo (por ejemplo,
    abrió una ola en el medio), falla con `EVENT_CHANGED` en vez de aplicar otro efecto.
    Las notificaciones (escenario 10) las genera quien llama, después del commit.
    """
    plan = _plan(
        db,
        club_id,
        event_id,
        fecha_hora,
        other_fields=other_fields,
        now=asegurar_utc(now or utcnow()),
        expected_version=expected_version,
        for_update=True,
    )
    if expected_schedule_effect is not None and (
        expected_schedule_effect != plan.impact.effect.value
        or expected_merged_into_order != plan.impact.merged_into_order
    ):
        raise error(
            status.HTTP_409_CONFLICT,
            "EVENT_CHANGED",
            "El evento cambió mientras lo editabas. Revisá los datos actuales y volvé a "
            "intentar.",
        )
    event = plan.event
    reprogramming = EventReprogramming(
        id=uuid.uuid4(),
        club_id=club_id,
        event_id=event.id_interno,
        previous_fecha_hora=plan.previous_start,
        new_fecha_hora=plan.new_start,
        schedule_effect=plan.impact.effect.value,
        reprogrammed_by_id=admin.id,
    )
    db.add(reprogramming)
    event.fecha_hora = plan.new_start
    event.cancelado_por_el_club = False
    event.version += 1
    _apply_to_schedule(db, admin, plan)
    audit.record(
        db,
        "event.rescheduled",
        actor_id=admin.id,
        entity="event",
        entity_id=event.id_interno,
        reprogramming_id=str(reprogramming.id),
        schedule_effect=plan.impact.effect.value,
        previous={"fecha_hora": plan.previous_start.isoformat()},
        new={"fecha_hora": plan.new_start.isoformat()},
    )
    db.commit()
    db.refresh(event)
    return Rescheduled(
        PublishedEvent(event, _find_schedule(db, event.id_interno)),
        reprogramming.id,
        plan,
    )

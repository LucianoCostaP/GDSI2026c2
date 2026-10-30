"""Lectura de los datos de entrada del ranking (HU-25, Ciclos 3a y 3b).

Esta capa solo consulta la base y le pasa datos crudos a los módulos puros
`scoring.attendance_inputs` y `scoring.institutional_inputs`. Todo se filtra por `club_id` y
nada se escribe.
"""

import uuid
from collections import defaultdict
from collections.abc import Collection
from datetime import date, datetime, time

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..core.date_utils import BUENOS_AIRES_TZ, a_hora_buenos_aires
from ..models import (
    ActividadRecurrenteDB,
    AsistenciaDB,
    CargaParticipacionDB,
    EstadoCargaParticipacion,
    EventoVisibleDB,
    TipoEvento,
    TipoParticipacion,
)
from ..scoring.attendance_inputs import MatchEvent
from ..scoring.institutional_inputs import (
    POINTS_PER_MONTH,
    ActivityRecord,
    InstitutionalEvent,
)


def load_loaded_matches(
    db: Session, club_id: uuid.UUID, *, window_start: date, until: datetime
) -> list[MatchEvent]:
    """Partidos del club que cuentan para la asistencia.

    Cuentan los de tipo Partido, con clase, de la ventana (desde las 00:00 de Buenos Aires del
    `window_start`), ya jugados (`fecha_hora <= until`) y con una carga de asistencia exitosa
    (HU-24). Un partido sin carga, o con una carga pendiente de aprobación o reemplazada, se
    ignora: no es una ausencia.
    """
    window_from = datetime.combine(window_start, time.min, tzinfo=BUENOS_AIRES_TZ)
    attendance_loaded = exists().where(
        CargaParticipacionDB.club_id == EventoVisibleDB.club_id,
        CargaParticipacionDB.tipo == TipoParticipacion.ASISTENCIA.value,
        CargaParticipacionDB.evento_id_externo == EventoVisibleDB.id_externo,
        CargaParticipacionDB.estado == EstadoCargaParticipacion.SUCCESSFUL.value,
    )
    rows = db.execute(
        select(
            EventoVisibleDB.id_externo,
            EventoVisibleDB.fecha_hora,
            EventoVisibleDB.clase,
        )
        .where(
            EventoVisibleDB.club_id == club_id,
            EventoVisibleDB.tipo == TipoEvento.PARTIDO.value,
            EventoVisibleDB.clase.is_not(None),
            EventoVisibleDB.fecha_hora >= window_from,
            EventoVisibleDB.fecha_hora <= until,
            attendance_loaded,
        )
        .order_by(EventoVisibleDB.fecha_hora, EventoVisibleDB.id_externo)
    )

    matches: list[MatchEvent] = []
    for event_id, played_at, match_class in rows:
        assert match_class is not None  # la consulta ya descartó los partidos sin clase
        matches.append(
            MatchEvent(
                event_id=event_id,
                day=a_hora_buenos_aires(played_at).date(),
                match_class=match_class,
            )
        )
    return matches


def load_attended_event_ids_by_dni(
    db: Session, club_id: uuid.UUID, event_ids: Collection[str]
) -> dict[str, set[str]]:
    """Para cada DNI del club, los eventos (de `event_ids`) a los que asistió."""
    attended: dict[str, set[str]] = defaultdict(set)
    if not event_ids:
        return attended
    rows = db.execute(
        select(AsistenciaDB.dni, AsistenciaDB.evento_id_externo).where(
            AsistenciaDB.club_id == club_id,
            AsistenciaDB.evento_id_externo.in_(event_ids),
        )
    )
    for dni, event_id in rows:
        attended[dni].add(event_id)
    return attended

def load_institutional_events_by_dni(
    db: Session, club_id: uuid.UUID, *, window_start: date, until: datetime
) -> dict[str, list[InstitutionalEvent]]:
    """Para cada DNI del club, los eventos institucionales a los que asistió (HU-25 FR-009).

    Un evento cuenta si es de tipo Institucional, tiene los puntos con los que se publicó,
    cae en la vigencia (desde las 00:00 de Buenos Aires de `window_start`) y ya ocurrió.
    `Ak = 1` es que exista el registro de asistencia del socio al evento.
    """
    window_from = datetime.combine(window_start, time.min, tzinfo=BUENOS_AIRES_TZ)
    rows = db.execute(
        select(
            AsistenciaDB.dni,
            EventoVisibleDB.id_externo,
            EventoVisibleDB.fecha_hora,
            EventoVisibleDB.puntos,
        )
        .join(
            EventoVisibleDB,
            (EventoVisibleDB.club_id == AsistenciaDB.club_id)
            & (EventoVisibleDB.id_externo == AsistenciaDB.evento_id_externo),
        )
        .where(
            AsistenciaDB.club_id == club_id,
            EventoVisibleDB.tipo == TipoEvento.INSTITUCIONAL.value,
            EventoVisibleDB.puntos.is_not(None),
            EventoVisibleDB.fecha_hora >= window_from,
            EventoVisibleDB.fecha_hora <= until,
        )
        .order_by(EventoVisibleDB.fecha_hora, EventoVisibleDB.id_externo)
    )
    events: dict[str, list[InstitutionalEvent]] = defaultdict(list)
    for dni, event_id, held_at, points in rows:
        assert points is not None  # la consulta ya descartó los eventos sin puntos
        events[dni].append(
            InstitutionalEvent(
                event_id=event_id,
                day=a_hora_buenos_aires(held_at).date(),
                points=points,
            )
        )
    return events


def load_activities_by_dni(
    db: Session, club_id: uuid.UUID, *, window_start: date, calculation_date: date
) -> dict[str, list[ActivityRecord]]:
    """Para cada DNI del club, sus registros de actividad que se tocan con la vigencia."""
    rows = db.execute(
        select(
            ActividadRecurrenteDB.dni,
            ActividadRecurrenteDB.tipo,
            ActividadRecurrenteDB.fecha_desde,
            ActividadRecurrenteDB.fecha_hasta,
        )
        .where(
            ActividadRecurrenteDB.club_id == club_id,
            ActividadRecurrenteDB.tipo.in_(list(POINTS_PER_MONTH)),
            ActividadRecurrenteDB.fecha_hasta >= window_start,
            ActividadRecurrenteDB.fecha_desde <= calculation_date,
        )
        .order_by(ActividadRecurrenteDB.fecha_desde)
    )
    activities: dict[str, list[ActivityRecord]] = defaultdict(list)
    for dni, kind, start, end in rows:
        activities[dni].append(ActivityRecord(kind=kind, start=start, end=end))
    return activities
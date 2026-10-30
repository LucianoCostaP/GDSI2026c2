"""Lectura de los datos de entrada del ranking (HU-25, Ciclo 3a).

Esta capa solo consulta la base y le pasa datos crudos al módulo puro
`scoring.attendance_inputs`. Todo se filtra por `club_id` y nada se escribe.
"""

import uuid
from collections import defaultdict
from collections.abc import Collection
from datetime import date, datetime, time

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..core.date_utils import BUENOS_AIRES_TZ, a_hora_buenos_aires
from ..models import (
    AsistenciaDB,
    CargaParticipacionDB,
    EstadoCargaParticipacion,
    EventoVisibleDB,
    TipoEvento,
    TipoParticipacion,
)
from ..scoring.attendance_inputs import MatchEvent


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
    return [
        MatchEvent(
            event_id=event_id,
            day=a_hora_buenos_aires(played_at).date(),
            match_class=match_class,
        )
        for event_id, played_at, match_class in rows
    ]


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
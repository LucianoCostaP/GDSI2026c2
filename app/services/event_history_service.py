"""HU-15: consultas del historial de eventos del Socio.

Un evento entra al historial si es del club del Socio y tiene una asistencia definitiva de su
documento (`asistencias`, HU-24). Valen los eventos publicados y los históricos. El orden y el
armado de cada ítem son lógica pura (`event_history`).
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.date_utils import asegurar_utc
from ..models import AsistenciaDB, EventoPendienteDB, EventoVisibleDB, User
from .event_history import AttendedEvent, HistoryItem, build_history
from .ranking_service import socio_of


def _tipo(value: Any) -> str:
    return str(getattr(value, "value", value))


def attended_events(db: Session, club_id: uuid.UUID, dni: str) -> list[AttendedEvent]:
    """Eventos del club, publicados o históricos, con asistencia definitiva de ese documento."""
    attended_ids = select(AsistenciaDB.evento_id_externo).where(
        AsistenciaDB.club_id == club_id, AsistenciaDB.dni == dni
    )
    published = db.scalars(
        select(EventoVisibleDB).where(
            EventoVisibleDB.club_id == club_id,
            EventoVisibleDB.id_externo.in_(attended_ids),
        )
    )
    historical = db.scalars(
        select(EventoPendienteDB).where(
            EventoPendienteDB.club_id == club_id,
            EventoPendienteDB.es_historico.is_(True),
            EventoPendienteDB.id_externo.in_(attended_ids),
        )
    )
    events: list[EventoVisibleDB | EventoPendienteDB] = [*published, *historical]
    return [
        AttendedEvent(
            id_interno=event.id_interno,
            titulo=event.titulo,
            fecha_hora=event.fecha_hora,
            tipo=_tipo(event.tipo),
        )
        for event in events
    ]


def _item_out(item: HistoryItem) -> dict[str, Any]:
    event = item.event
    return {
        "id_interno": event.id_interno,
        "titulo": event.titulo,
        "fecha_hora": asegurar_utc(event.fecha_hora).isoformat(),
    }


def member_history(
    db: Session, member_user: User, club_id: uuid.UUID
) -> dict[str, Any]:
    """Historial de eventos del Socio de la sesión, del más reciente al más antiguo."""
    socio = socio_of(db, member_user, club_id)
    events = attended_events(db, club_id, socio.dni) if socio is not None else []
    items = build_history(events)
    return {"total": len(items), "events": [_item_out(item) for item in items]}

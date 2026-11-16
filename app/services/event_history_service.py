"""HU-15: consultas del historial de eventos del Socio.

Un evento entra al historial si es del club del Socio y tiene una asistencia definitiva de su
documento (`asistencias`, HU-24). Valen los eventos publicados y los históricos. El orden, la
versión de reglas de cada evento y el armado de la respuesta son lógica pura (`event_history`).

El Socio también puede leer una versión de reglas de su club por su número (decisión 50), con la
misma explicación que HU-13.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.date_utils import asegurar_utc
from ..models import (
    AsistenciaDB,
    EventoPendienteDB,
    EventoVisibleDB,
    RulesVersion,
    RulesVersionState,
    User,
)
from .event_history import AttendedEvent, RulesRef, build_history, history_response
from .formula_service import error, explanation_of
from .ranking_service import socio_of

RULES_VERSION_NOT_FOUND_MESSAGE = "No encontramos esa versión de reglas."


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


def rules_timeline(db: Session, club_id: uuid.UUID) -> list[RulesRef]:
    """Número y fecha de publicación de cada versión de reglas del club."""
    rows = db.execute(
        select(RulesVersion.number, RulesVersion.published_at).where(
            RulesVersion.club_id == club_id
        )
    )
    return [
        RulesRef(number=number, published_at=published_at)
        for number, published_at in rows
    ]


def member_history(
    db: Session, member_user: User, club_id: uuid.UUID
) -> dict[str, Any]:
    """Historial de eventos del Socio de la sesión, del más reciente al más antiguo."""
    socio = socio_of(db, member_user, club_id)
    events = attended_events(db, club_id, socio.dni) if socio is not None else []
    return history_response(build_history(events, rules_timeline(db, club_id)))


def member_rules_version(
    db: Session, club_id: uuid.UUID, number: int
) -> dict[str, Any]:
    """Una versión de reglas del club, vigente o reemplazada, con la explicación de HU-13.

    Nunca incluye quién la publicó. Una versión de otro club o inexistente es 404.
    """
    rules = db.scalar(
        select(RulesVersion).where(
            RulesVersion.club_id == club_id, RulesVersion.number == number
        )
    )
    if rules is None:
        raise error(404, "RULES_VERSION_NOT_FOUND", RULES_VERSION_NOT_FOUND_MESSAGE)
    descriptor, explanation = explanation_of(rules)
    return {
        "rules_version": rules.number,
        "published_at": asegurar_utc(rules.published_at).isoformat(),
        "in_force": rules.state == RulesVersionState.IN_FORCE,
        "formula": {
            "id": descriptor.id,
            "version": descriptor.version,
            "name": descriptor.name,
        },
        "explanation": explanation,
    }

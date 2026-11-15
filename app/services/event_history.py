"""HU-15: historial de eventos del Socio. Lógica pura, sin base de datos ni reloj.

La capa de datos (`event_history_service`) trae los eventos a los que el Socio asistió; acá se
ordenan, se les asigna la versión de reglas vigente en su fecha y se arma la respuesta. La clase
de un Partido nunca llega hasta acá: `AttendedEvent` no la tiene, así que no se puede exponer por
error (como en HU-17).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..core.date_utils import asegurar_utc, formatear_tipo_evento

RULES_URL = "/member/scoring/rules/{number}"
NO_RULES_MESSAGE = "No había reglas de puntaje publicadas en ese momento."


@dataclass(frozen=True)
class AttendedEvent:
    """Un evento pasado del club con asistencia definitiva del Socio."""

    id_interno: str
    titulo: str
    fecha_hora: datetime
    tipo: str


@dataclass(frozen=True)
class RulesRef:
    """Una versión de reglas del club y cuándo se publicó."""

    number: int
    published_at: datetime


@dataclass(frozen=True)
class HistoryItem:
    """Un evento del historial del Socio y la versión de reglas vigente en su fecha."""

    event: AttendedEvent
    rules: RulesRef | None = None


def rules_in_force_at(
    versions: Iterable[RulesRef], moment: datetime
) -> RulesRef | None:
    """La versión vigente en `moment`: la de publicación más reciente que no sea posterior.

    Una versión publicada exactamente en `moment` ya rige. Sin versiones publicadas hasta ese
    momento no hay reglas (`None`). Todo se compara en UTC.
    """
    instant = asegurar_utc(moment)
    published = [v for v in versions if asegurar_utc(v.published_at) <= instant]
    return max(
        published,
        key=lambda v: (asegurar_utc(v.published_at), v.number),
        default=None,
    )


def build_history(
    events: Iterable[AttendedEvent], versions: Iterable[RulesRef] = ()
) -> list[HistoryItem]:
    """Un ítem por evento, del más reciente al más antiguo, con las reglas vigentes en su fecha.

    Dos eventos en el mismo instante se ordenan por `id_interno`, para que el orden sea estable.
    Un evento repetido aparece una sola vez.
    """
    rules = list(versions)
    unique = {event.id_interno: event for event in events}.values()
    ordered = sorted(
        unique,
        key=lambda event: (
            -asegurar_utc(event.fecha_hora).timestamp(),
            event.id_interno,
        ),
    )
    return [
        HistoryItem(event=event, rules=rules_in_force_at(rules, event.fecha_hora))
        for event in ordered
    ]


def _rules_out(rules: RulesRef | None) -> dict[str, Any] | None:
    if rules is None:
        return None
    return {
        "number": rules.number,
        "published_at": asegurar_utc(rules.published_at).isoformat(),
        "url": RULES_URL.format(number=rules.number),
    }


def _event_out(item: HistoryItem) -> dict[str, Any]:
    event = item.event
    return {
        "id_interno": event.id_interno,
        "titulo": event.titulo,
        # En UTC; el front la muestra en hora de Buenos Aires.
        "fecha_hora": asegurar_utc(event.fecha_hora).isoformat(),
        "tipo": formatear_tipo_evento(event.tipo),
        "rules_version": _rules_out(item.rules),
        "rules_message": None if item.rules is not None else NO_RULES_MESSAGE,
    }


def history_response(items: list[HistoryItem]) -> dict[str, Any]:
    """Respuesta del historial: el total y cada evento con su fecha, su tipo y sus reglas."""
    return {"total": len(items), "events": [_event_out(item) for item in items]}

"""HU-15: historial de eventos del Socio. Lógica pura, sin base de datos ni reloj.

La capa de datos (`event_history_service`) trae los eventos a los que el Socio asistió; acá se
ordenan y se arma la respuesta. La clase de un Partido nunca llega hasta acá: `AttendedEvent` no
la tiene, así que no se puede exponer por error (como en HU-17).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..core.date_utils import asegurar_utc, formatear_tipo_evento


@dataclass(frozen=True)
class AttendedEvent:
    """Un evento pasado del club con asistencia definitiva del Socio."""

    id_interno: str
    titulo: str
    fecha_hora: datetime
    tipo: str


@dataclass(frozen=True)
class HistoryItem:
    """Un evento del historial del Socio."""

    event: AttendedEvent


def build_history(events: Iterable[AttendedEvent]) -> list[HistoryItem]:
    """Un ítem por evento, del más reciente al más antiguo.

    Dos eventos en el mismo instante se ordenan por `id_interno`, para que el orden sea estable.
    Un evento repetido aparece una sola vez.
    """
    unique = {event.id_interno: event for event in events}.values()
    ordered = sorted(
        unique,
        key=lambda event: (
            -asegurar_utc(event.fecha_hora).timestamp(),
            event.id_interno,
        ),
    )
    return [HistoryItem(event=event) for event in ordered]


def _event_out(item: HistoryItem) -> dict[str, Any]:
    event = item.event
    return {
        "id_interno": event.id_interno,
        "titulo": event.titulo,
        # En UTC; el front la muestra en hora de Buenos Aires.
        "fecha_hora": asegurar_utc(event.fecha_hora).isoformat(),
        "tipo": formatear_tipo_evento(event.tipo),
    }


def history_response(items: list[HistoryItem]) -> dict[str, Any]:
    """Respuesta del historial: el total y cada evento con su fecha y su tipo."""
    return {"total": len(items), "events": [_event_out(item) for item in items]}

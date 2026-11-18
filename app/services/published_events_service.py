"""Eventos publicados que el Admin puede reprogramar o retirar (HU-23B).

El club sale siempre de la cuenta del Admin (decisión 34). El servicio recibe `now` solo
para los tests; si no llega, manda el reloj del servidor.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EventoVisibleDB, TipoEvento, WaveSchedule, utcnow

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

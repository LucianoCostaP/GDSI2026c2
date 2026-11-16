"""Servicio de cimientos para notificaciones a los socios sobre eventos (HU-23).

Permite registrar eventos notificables (reprogramación, retiro, restauración)
y ofrece una interfaz limpia para que el equipo que implementa el sistema
de notificaciones por app/email consuma los eventos encolados sin acoplarse
a la lógica interna de eventos.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.notifications import EventNotificationDB, TipoNotificacionEvento


def encolar_notificacion_evento(
    db: Session,
    *,
    club_id: uuid.UUID,
    event_id: str,
    tipo: TipoNotificacionEvento | str,
    titulo: str,
    mensaje: str,
    datos: dict[str, Any] | None = None,
) -> EventNotificationDB:
    """Encola un evento notificable para que el servicio de notificaciones lo despache."""
    tipo_str = tipo.value if isinstance(tipo, TipoNotificacionEvento) else str(tipo)
    notif = EventNotificationDB(
        club_id=club_id,
        event_id=event_id,
        tipo_notificacion=tipo_str,
        titulo=titulo,
        mensaje=mensaje,
        datos_evento=datos or {},
        creado_en=datetime.now(UTC),
        procesado=False,
    )
    db.add(notif)
    return notif


def notificar_reprogramacion(
    db: Session,
    *,
    club_id: uuid.UUID,
    event_id: str,
    titulo_evento: str,
    cambios: dict[str, Any],
) -> EventNotificationDB:
    """Cimiento para notificar a los socios que un evento fue reprogramado."""
    return encolar_notificacion_evento(
        db,
        club_id=club_id,
        event_id=event_id,
        tipo=TipoNotificacionEvento.EVENTO_REPROGRAMADO,
        titulo=f"Evento reprogramado: {titulo_evento}",
        mensaje=f"Se actualizaron la fecha, horario o sede del evento '{titulo_evento}'.",
        datos=cambios,
    )


def notificar_retiro(
    db: Session,
    *,
    club_id: uuid.UUID,
    event_id: str,
    titulo_evento: str,
    motivo: str,
) -> EventNotificationDB:
    """Cimiento para notificar a los socios que un evento fue retirado."""
    return encolar_notificacion_evento(
        db,
        club_id=club_id,
        event_id=event_id,
        tipo=TipoNotificacionEvento.EVENTO_RETIRADO,
        titulo=f"Evento cancelado: {titulo_evento}",
        mensaje=f"El evento '{titulo_evento}' ha sido retirado. Motivo: {motivo}",
        datos={"motivo": motivo},
    )


def notificar_restauracion(
    db: Session,
    *,
    club_id: uuid.UUID,
    event_id: str,
    titulo_evento: str,
) -> EventNotificationDB:
    """Cimiento para notificar a los socios que un evento fue restaurado."""
    return encolar_notificacion_evento(
        db,
        club_id=club_id,
        event_id=event_id,
        tipo=TipoNotificacionEvento.EVENTO_RESTAURADO,
        titulo=f"Evento restaurado: {titulo_evento}",
        mensaje=f"El evento '{titulo_evento}' vuelve a estar programado.",
        datos={},
    )


def obtener_notificaciones_pendientes(
    db: Session,
    club_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[EventNotificationDB]:
    """Retorna las notificaciones pendientes de procesar para el equipo de notificaciones."""
    stmt = select(EventNotificationDB).where(EventNotificationDB.procesado.is_(False))
    if club_id:
        stmt = stmt.where(EventNotificationDB.club_id == club_id)
    stmt = stmt.order_by(EventNotificationDB.creado_en.asc()).limit(limit)
    return list(db.scalars(stmt))


def marcar_notificaciones_procesadas(
    db: Session,
    ids: list[uuid.UUID],
) -> None:
    """Marca las notificaciones como despachadas por la app o correo."""
    ahora = datetime.now(UTC)
    for notif in db.scalars(
        select(EventNotificationDB).where(EventNotificationDB.id.in_(ids))
    ):
        notif.procesado = True
        notif.procesado_en = ahora

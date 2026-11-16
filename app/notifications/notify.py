"""El contrato único para generar notificaciones (notificaciones §4).

`notify(type, occurrence_key, recipients, reference, params)`:

- crea una notificación `unread` por destinatario, con el texto del catálogo congelado;
- no duplica: el par (cuenta, `occurrence_key`) es único, así que reintentos y dobles corridas
  no crean nada;
- nunca le tira un error a quien lo llama: se registra en el log y el proceso que lo disparó
  sigue (publicación, ranking, cronograma);
- se llama después de confirmar el cambio que lo dispara.

El encolado del correo llega con HU-19 user story 2.
"""

import logging
import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from ..models import Notification, NotificationState
from ..models.auth import utcnow
from .catalog import BY_KEY

logger = logging.getLogger(__name__)

_BATCH = 1000


def notify(
    db: Session,
    type: str,
    occurrence_key: str,
    recipients: Iterable[int],
    *,
    club_id: uuid.UUID,
    reference: dict[str, Any],
    params: dict[str, str],
    now: datetime | None = None,
) -> int:
    """Genera la notificación `type` para cada cuenta de `recipients` (ids de `users`) y
    devuelve cuántas creó. Un tipo inactivo no genera nada (notificaciones §2)."""
    try:
        entry = BY_KEY[type]
        if not entry.active:
            return 0
        message = entry.message.format(**params)
        created_at = now or utcnow()
        rows = [
            {
                "club_id": club_id,
                "user_id": user_id,
                "type": type,
                "reference": reference,
                "title": entry.title,
                "message": message,
                "created_at": created_at,
                "state": NotificationState.UNREAD,
                "occurrence_key": occurrence_key,
            }
            for user_id in dict.fromkeys(recipients)
        ]
        if not rows:
            return 0
        dialect = postgresql if db.get_bind().dialect.name == "postgresql" else sqlite
        created = 0
        # En tandas: un ranking avisa a todo el padrón (HU-19, caso borde "Volume").
        for start in range(0, len(rows), _BATCH):
            result = db.execute(
                dialect.insert(Notification)
                .values(rows[start : start + _BATCH])
                .on_conflict_do_nothing(index_elements=["user_id", "occurrence_key"])
                .returning(Notification.id)
            )
            created += len(result.all())
        db.commit()
    except Exception:
        db.rollback()
        # Sin datos personales: solo el tipo y la ocurrencia (notificaciones §8).
        logger.exception(
            "No se pudo generar la notificación %s (%s)", type, occurrence_key
        )
        return 0
    logger.info("Notificación %s (%s): %d creadas", type, occurrence_key, created)
    return created

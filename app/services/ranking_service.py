"""Consultas sobre el ranking que usan otras historias.

HU-25 (cálculo del ranking) todavía no existe: no hay tabla de rankings. Hasta entonces no hay
ranking completado y la consulta responde `None`. Cuando HU-25 guarde sus rankings
(`status = completed`, con la versión de reglas que usó cada uno, decisión 41), reemplaza el
cuerpo de esta función y agrega el test de integración del escenario 5 de HU-13 sin mocks.
"""

import uuid

from sqlalchemy.orm import Session


def latest_completed_ranking_rules_number(
    db: Session, club_id: uuid.UUID
) -> int | None:
    """Número de la versión de reglas que usó el último ranking completado del club, o
    `None` si el club todavía no tiene ninguno."""
    return None

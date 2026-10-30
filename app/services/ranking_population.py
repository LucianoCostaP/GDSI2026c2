"""Población del ranking (HU-25, Ciclo 2).

Define quiénes entran al cálculo: los socios del club con la cuota al día y sin baja, hayan
activado o no su cuenta. Los morosos quedan fuera, pero este módulo solo *lee* `socios`:
sus asistencias y actividades no se tocan, así que el historial sigue almacenado y vuelve a
contar cuando pagan (spec HU-25, edge case "Ranking population").

Es la única definición de la población. Quien la necesite (el cálculo, una simulación) tiene
que pedirla acá en lugar de repetir el filtro.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import EstadoCuota, Socio


def select_population(db: Session, club_id: uuid.UUID) -> list[Socio]:
    """Socios del club que entran al ranking, ordenados por DNI para que sea determinístico.

    - Cuota al día: los morosos quedan afuera (se evalúa al momento del cálculo).
    - Sin baja (`activo`): una baja sale de la población del próximo ranking (HU-43, esc. 9).
    - Sin mirar la cuenta: un socio que no activó la suya también se rankea.
    """
    return list(
        db.scalars(
            select(Socio)
            .where(
                Socio.club_id == club_id,
                Socio.activo.is_(True),
                Socio.estado_cuota == EstadoCuota.AL_DIA.value,
            )
            .order_by(Socio.dni)
        )
    )
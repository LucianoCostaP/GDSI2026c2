"""Ejecución del cálculo del ranking de un club (HU-25).

Va aparte de `ranking_service` porque `formula_service` importa ese módulo: si éste
importara a `formula_service` (para las reglas en vigor) se armaría un ciclo.

Ciclo 1 (esqueleto): corre de punta a punta con las reglas vigentes y guarda una entrada
por socio, pero todavía sin motor de scoring (los componentes salen en cero), con un
desempate provisorio por DNI (Ciclo 4) y de forma síncrona (Ciclo 5).

Ciclo 2: la población sale de `ranking_population` (cuota al día y sin baja, con o sin
cuenta activada).

Ciclo 3a: cada entrada guarda en `inputs["attendance"]` los insumos de asistencia del socio
(ventana, partidos por clase, asistidos y distancia). Los componentes siguen en cero hasta el
motor de scoring.

Ciclo 3b: y en `inputs["institutional"]` los puntos de participación institucional (eventos
a los que asistió y meses de actividades recurrentes de los últimos 365 días). Los componentes
siguen en cero hasta que se conecte el motor de scoring.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ..core.date_utils import a_hora_buenos_aires
from ..models import Ranking, RankingEntry, RankingState, Socio, User, utcnow
from ..scoring.attendance_inputs import attendance_window_start, build_attendance_inputs
from ..scoring.components import empty_components, total_of
from ..scoring.institutional_inputs import (
    build_institutional_inputs,
    institutional_window_start,
)
from .formula_service import require_rules_in_force
from .ranking_inputs import (
    load_activities_by_dni,
    load_attended_event_ids_by_dni,
    load_institutional_events_by_dni,
    load_loaded_matches,
)
from .ranking_population import select_population

def _score(socio: Socio) -> dict[str, Decimal]:
    """Componentes del socio. Reemplazar por el motor de scoring (Ciclos 0 y 3)."""
    return empty_components()


def start_run(
    db: Session,
    admin: User,
    club_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> Ranking:
    """Calcula el ranking del club con las reglas en vigor y lo deja completado.

    `now` es el reloj inyectable (constitución, principio 6): por defecto, la hora actual.
    """
    rules = require_rules_in_force(db, club_id)
    started_at = now if now is not None else utcnow()

    ranking = Ranking(
        club_id=club_id,
        rules_version_id=rules.id,
        status=RankingState.RUNNING,
        calculation_date=a_hora_buenos_aires(started_at).date(),
        calculated_at=started_at,
        population_size=0,
        requested_by_id=admin.id,
    )
    db.add(ranking)
    db.flush()

    socios = select_population(db, club_id)
    matches = load_loaded_matches(
        db,
        club_id,
        window_start=attendance_window_start(ranking.calculation_date),
        until=started_at,
    )
    attended_by_dni = load_attended_event_ids_by_dni(
        db, club_id, {match.event_id for match in matches}
    )

    institutional_start = institutional_window_start(ranking.calculation_date)
    events_by_dni = load_institutional_events_by_dni(
        db, club_id, window_start=institutional_start, until=started_at
    )
    activities_by_dni = load_activities_by_dni(
        db,
        club_id,
        window_start=institutional_start,
        calculation_date=ranking.calculation_date,
    )

    scored: list[tuple[Socio, dict[str, Decimal], Decimal, dict[str, Any]]] = []
    for socio in socios:
        attendance = build_attendance_inputs(
            alta=socio.fecha_alta,
            distance_km=socio.distancia_km,
            calculation_date=ranking.calculation_date,
            events=matches,
            attended_event_ids=attended_by_dni.get(socio.dni, set()),
        )
        institutional = build_institutional_inputs(
            calculation_date=ranking.calculation_date,
            attended_events=events_by_dni.get(socio.dni, []),
            activities=activities_by_dni.get(socio.dni, []),
        )
        components = _score(socio)
        snapshot = {
            "attendance": attendance.as_dict(),
            "institutional": institutional.as_dict(),
        }
        scored.append((socio, components, total_of(components), snapshot))
    # Mayor total primero; el desempate completo llega en el Ciclo 4.
    scored.sort(key=lambda item: (-item[2], item[0].dni))

    for position, (socio, components, total, inputs) in enumerate(scored, start=1):
        db.add(
            RankingEntry(
                ranking_id=ranking.id,
                socio_id=socio.id,
                position=position,
                total=total,
                inputs=inputs,
                **components,
            )
        )

    ranking.population_size = len(scored)
    ranking.mark_completed(utcnow())
    db.commit()
    return ranking
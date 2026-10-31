"""Ejecución del cálculo del ranking de un club (HU-25).

Va aparte de `ranking_service` porque `formula_service` importa ese módulo: si éste
importara a `formula_service` (para las reglas en vigor) se armaría un ciclo.

Ciclo 1 (esqueleto): corre de punta a punta con las reglas vigentes y guarda una entrada
por socio, pero todavía sin motor de scoring (los componentes salen en cero), con un
desempate provisorio por DNI (Ciclo 4) y de forma síncrona (Ciclo 5).

Ciclo 2: la población sale de `ranking_population` (cuota al día y sin baja, con o sin
cuenta activada).

Ciclos 3a a 3c: por cada socio se arman los insumos de asistencia, de participación
institucional y de pertenencia (antigüedad, edad y alta); se calculan los seis componentes con
el motor de scoring y los parámetros de la versión en vigor; y la entrada guarda componentes,
total, posición y la instantánea de esos insumos en `inputs`.

Ciclo 4: el orden y las posiciones salen de `scoring.ranking_order` (total y desempates por
antigüedad, edad y documento), así que las posiciones son únicas y consecutivas.

Ciclo 5 (síncrono): una sola corrida a la vez por club. La corrida se registra y se confirma
como `running` antes de calcular, así los demás pedidos la ven (409 al intentar otra y estado
consultable) y el índice único parcial la respalda ante pedidos concurrentes. Una falla durante
el cálculo la deja `failed` y nunca `running`, para no bloquear al club.

Ciclo 7: una falla durante el cálculo deja la corrida `failed` con su detalle, no guarda
ninguna entrada (todo se deshace) y no toca el ranking vigente; al Admin se le informa con un
mensaje seguro. Una corrida `running` de más de 15 minutos se da por abandonada (el proceso
pudo morir) y pasa a `failed`, para no bloquear al club.
"""

import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..core.date_utils import a_hora_buenos_aires
from ..models import Ranking, RankingEntry, RankingState, User, utcnow
from ..scoring.attendance_inputs import attendance_window_start, build_attendance_inputs
from ..scoring.engine import ScoringParameters, calculate_score
from ..scoring.institutional_inputs import (
    build_institutional_inputs,
    institutional_window_start,
)
from ..scoring.membership_inputs import build_membership_inputs
from ..scoring.ranking_order import RankingCandidate, assign_positions
from ..scoring.snapshot import build_scoring_inputs
from .formula_service import error, require_rules_in_force
from .ranking_inputs import (
    load_activities_by_dni,
    load_attended_event_ids_by_dni,
    load_institutional_events_by_dni,
    load_loaded_matches,
)
from .ranking_population import select_population

logger = logging.getLogger(__name__)

RUN_IN_PROGRESS = "RANKING_RUN_IN_PROGRESS"
RUN_FAILED = "RANKING_RUN_FAILED"
NO_RANKING_RUN = "NO_RANKING_RUN"
RUN_FAILED_MESSAGE = (
    "No se pudo completar el cálculo del ranking. El ranking anterior sigue vigente."
)
# Una corrida en curso más vieja que esto se da por abandonada (NFR: el cálculo dura menos).
RUN_TIMEOUT = timedelta(minutes=15)
ABANDONED_MESSAGE = (
    "Corrida abandonada: superó los 15 minutos en curso sin terminar "
    "(el proceso pudo haberse interrumpido)."
)


def get_running_run(db: Session, club_id: uuid.UUID) -> Ranking | None:
    """La corrida en curso del club, si hay una."""
    return db.scalar(
        select(Ranking).where(
            Ranking.club_id == club_id, Ranking.status == RankingState.RUNNING
        )
    )


def get_latest_run(db: Session, club_id: uuid.UUID) -> Ranking | None:
    """La corrida más reciente del club, en cualquier estado."""
    return db.scalar(
        select(Ranking)
        .where(Ranking.club_id == club_id)
        .order_by(Ranking.id.desc())
        .limit(1)
    )


def fail_abandoned_runs(db: Session, club_id: uuid.UUID, now: datetime) -> int:
    """Pasa a `failed` las corridas del club que llevan más de 15 minutos en curso."""
    stale = db.scalars(
        select(Ranking).where(
            Ranking.club_id == club_id,
            Ranking.status == RankingState.RUNNING,
            Ranking.calculated_at < now - RUN_TIMEOUT,
        )
    ).all()
    for ranking in stale:
        ranking.mark_failed(ABANDONED_MESSAGE)
    if stale:
        db.commit()
    return len(stale)


def _run_in_progress(running: Ranking | None) -> HTTPException:
    details: dict[str, Any] = {}
    if running is not None:
        details = {
            "ranking_id": running.id,
            "calculated_at": running.calculated_at.isoformat(),
        }
    return error(
        status.HTTP_409_CONFLICT,
        RUN_IN_PROGRESS,
        "Ya hay un cálculo del ranking en curso.",
        **details,
    )


def _claim_run(
    db: Session,
    admin: User,
    club_id: uuid.UUID,
    rules_version_id: int,
    started_at: datetime,
) -> Ranking:
    """Registra la corrida como `running` y la confirma, o rechaza si ya hay una en curso."""
    fail_abandoned_runs(db, club_id, started_at)
    running = get_running_run(db, club_id)
    if running is not None:
        raise _run_in_progress(running)
    ranking = Ranking(
        club_id=club_id,
        rules_version_id=rules_version_id,
        status=RankingState.RUNNING,
        calculation_date=a_hora_buenos_aires(started_at).date(),
        calculated_at=started_at,
        population_size=0,
        requested_by_id=admin.id,
    )
    db.add(ranking)
    try:
        # Se confirma ya: mientras se calcula, la corrida es visible para los demás pedidos
        # y el índice único parcial frena a quien llegue al mismo tiempo.
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _run_in_progress(get_running_run(db, club_id)) from None
    return ranking


def _mark_failed(db: Session, run_id: int, error_message: str) -> None:
    ranking = db.get_one(Ranking, run_id)
    # Otro pedido pudo haberla dado por abandonada mientras tanto.
    if ranking.status == RankingState.RUNNING:
        ranking.mark_failed(error_message)
        db.commit()


def start_run(
    db: Session,
    admin: User,
    club_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> Ranking:
    """Calcula el ranking del club con las reglas en vigor y lo deja completado.

    `now` es el reloj inyectable (constitución, principio 6): por defecto, la hora actual.
    Rechaza con 409 si el club ya tiene una corrida en curso. Si el cálculo falla, deshace todo,
    deja la corrida `failed` con su detalle y responde 500 `RANKING_RUN_FAILED`; el ranking
    vigente no se toca.
    """
    rules = require_rules_in_force(db, club_id)
    params = ScoringParameters.from_values(rules.values)
    started_at = now if now is not None else utcnow()

    ranking = _claim_run(db, admin, club_id, rules.id, started_at)
    run_id = ranking.id
    try:
        _calculate_entries(db, ranking, club_id, params, started_at)
    except Exception as exc:
        # Nada de lo calculado queda guardado y la corrida nunca se queda en `running`.
        db.rollback()
        logger.exception("Falló el cálculo del ranking %s del club %s", run_id, club_id)
        _mark_failed(db, run_id, f"{type(exc).__name__}: {exc}")
        raise error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            RUN_FAILED,
            RUN_FAILED_MESSAGE,
            ranking_id=run_id,
        ) from exc
    return ranking


def _calculate_entries(
    db: Session,
    ranking: Ranking,
    club_id: uuid.UUID,
    params: ScoringParameters,
    started_at: datetime,
) -> None:
    """Calcula y guarda las entradas de la corrida y la completa, todo en una transacción."""
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

    scored: dict[uuid.UUID, tuple[dict[str, Decimal], dict[str, Any]]] = {}
    candidates: list[RankingCandidate] = []
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
        membership = build_membership_inputs(
            birth_date=socio.fecha_nacimiento,
            alta=socio.fecha_alta,
            previous_baja=socio.fecha_baja_previa,
            calculation_date=ranking.calculation_date,
        )
        score = calculate_score(
            build_scoring_inputs(attendance, institutional, membership), params
        )
        snapshot = {
            "attendance": attendance.as_dict(),
            "institutional": institutional.as_dict(),
            "membership": membership.as_dict(),
        }
        scored[socio.id] = (score.components, snapshot)
        candidates.append(
            RankingCandidate(
                socio_id=socio.id,
                total=score.total,
                seniority_start=membership.seniority_start,
                birth_date=membership.birth_date,
                dni=socio.dni,
            )
        )

    for position, candidate in assign_positions(candidates):
        components, inputs = scored[candidate.socio_id]
        db.add(
            RankingEntry(
                ranking_id=ranking.id,
                socio_id=candidate.socio_id,
                position=position,
                total=candidate.total,
                inputs=inputs,
                **components,
            )
        )

    ranking.population_size = len(candidates)
    ranking.mark_completed(utcnow())
    db.commit()

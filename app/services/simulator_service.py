"""Simulador de puntaje por asistencia (HU-18, `docs/contrato-api-simulador.md`).

Simula un solo evento sobre la instantánea que guardó el último ranking completado: no combina
otros próximos eventos (escenario 1) y no guarda nada (FR-004). Los puntajes salen del motor
único (`scoring.engine.calculate_score`) con las reglas de ese ranking.

Pendiente (próximos escenarios): evento ya empezado (3), aviso de reglas (8), distancia actual
(9) y posición estimada (10). Mientras tanto la posición de un Partido no se estima, que es lo
que corresponde con `position_projection_enabled` apagado (su valor por defecto).
"""

import uuid
from dataclasses import replace
from decimal import Decimal

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.date_utils import formatear_tipo_evento
from ..core.exceptions import PasioDe10Exception
from ..models import (
    EstadoCuota,
    EventoVisibleDB,
    RankingEntry,
    RulesVersion,
    User,
)
from ..models.enums import TipoEvento
from ..schemas.simulator import (
    CurrentStandingOut,
    HypothesisOut,
    PositionEstimateOut,
    SimulatedEventOut,
    SimulationOut,
    SimulationRankingOut,
)
from ..scoring.attendance_inputs import MATCH_CLASSES
from ..scoring.engine import ScoringInputs, ScoringParameters, calculate_score
from ..scoring.snapshot import scoring_inputs_from_snapshot
from .ranking_service import _socio_of, get_ranking_in_force

EVENT_NOT_FOUND_MESSAGE = "No encontramos el evento."
EVENT_NOT_SIMULABLE_MESSAGE = "Este evento ya no está disponible para simular."
NOT_IN_RANKING_MESSAGE = (
    "Para simular necesitás un puntaje calculado. Todavía no estás en el ranking."
)
POSITION_NOT_AVAILABLE_MESSAGE = (
    "No podemos estimar tu posición en este momento. Te mostramos solo tu puntaje."
)
INSTITUTIONAL_NOTICE = (
    "No asistir no cambia tu puntaje, pero tu posición puede bajar si otros socios "
    "suman puntos."
)


def _event_of_club(db: Session, club_id: uuid.UUID, event_id: str) -> EventoVisibleDB:
    """El evento publicado del club; uno de otro club responde igual que uno inexistente."""
    event = db.scalar(
        select(EventoVisibleDB).where(
            EventoVisibleDB.id_interno == event_id,
            EventoVisibleDB.club_id == club_id,
        )
    )
    if event is None:
        raise PasioDe10Exception(
            EVENT_NOT_FOUND_MESSAGE, status.HTTP_404_NOT_FOUND, "EVENT_NOT_FOUND"
        )
    is_match = event.tipo == TipoEvento.PARTIDO.value
    if (is_match and event.clase not in MATCH_CLASSES) or (
        not is_match
        and (event.tipo != TipoEvento.INSTITUCIONAL.value or not event.puntos)
    ):
        # Un Partido sin clase o un institucional sin puntos no entran en el cálculo.
        raise PasioDe10Exception(
            EVENT_NOT_SIMULABLE_MESSAGE, status.HTTP_409_CONFLICT, "EVENT_NOT_SIMULABLE"
        )
    return event


def _not_in_ranking() -> PasioDe10Exception:
    return PasioDe10Exception(
        NOT_IN_RANKING_MESSAGE, status.HTTP_409_CONFLICT, "NOT_IN_RANKING"
    )


def _with_event(
    base: ScoringInputs, event: EventoVisibleDB, *, attends: bool
) -> ScoringInputs:
    """Los insumos del socio con este evento sumado, según asista o no (escenarios 4 a 6)."""
    if event.tipo == TipoEvento.PARTIDO.value:
        match_class = str(event.clase)
        matches = dict(base.matches_by_class)
        matches[match_class] += 1
        attended = dict(base.attended_by_class)
        if attends:
            attended[match_class] += 1
        return replace(base, matches_by_class=matches, attended_by_class=attended)
    if attends:
        points = base.institutional_points + Decimal(event.puntos or 0)
        return replace(base, institutional_points=points)
    return base


def _hypothesis(score: Decimal, current: Decimal) -> HypothesisOut:
    return HypothesisOut(score=f"{score:.2f}", difference=f"{score - current:.2f}")


def simulate_event(
    db: Session, member_user: User, club_id: uuid.UUID, event_id: str
) -> SimulationOut:
    """HU-18: puntaje del socio si asiste y si no asiste a un evento, sin guardar nada."""
    event = _event_of_club(db, club_id, event_id)

    ranking = get_ranking_in_force(db, club_id)
    socio = _socio_of(db, member_user, club_id)
    # La cuota se lee del padrón en el momento, como en HU-14.
    if (
        ranking is None
        or socio is None
        or socio.estado_cuota != EstadoCuota.AL_DIA.value
    ):
        raise _not_in_ranking()
    entry = db.scalar(
        select(RankingEntry).where(
            RankingEntry.ranking_id == ranking.id, RankingEntry.socio_id == socio.id
        )
    )
    if entry is None:
        raise _not_in_ranking()

    rules = db.get(RulesVersion, ranking.rules_version_id)
    assert rules is not None  # clave foránea
    params = ScoringParameters.from_values(rules.values)
    base = scoring_inputs_from_snapshot(entry.inputs)
    current = entry.total
    attend = calculate_score(_with_event(base, event, attends=True), params).total
    not_attend = calculate_score(_with_event(base, event, attends=False), params).total

    is_match = event.tipo == TipoEvento.PARTIDO.value
    if is_match:
        estimate = PositionEstimateOut(
            status="unavailable",
            code="POSITION_NOT_AVAILABLE",
            reason="PROJECTION_DISABLED",
            message=POSITION_NOT_AVAILABLE_MESSAGE,
        )
    else:
        estimate = PositionEstimateOut(
            status="not_estimated",
            code=None,
            reason="INSTITUTIONAL_NOT_ESTIMATED",
            message=INSTITUTIONAL_NOTICE,
        )

    return SimulationOut(
        event=SimulatedEventOut(
            id=event.id_interno,
            titulo=event.titulo,
            tipo=formatear_tipo_evento(event.tipo),
            fecha_hora=event.fecha_hora,
            puntos=None if is_match else event.puntos,
        ),
        ranking=SimulationRankingOut(
            completed_at=ranking.completed_at,
            calculation_date=ranking.calculation_date,
            rules_version=rules.number,
        ),
        current=CurrentStandingOut(
            score=f"{current:.2f}",
            position=entry.position,
            ranked_total=ranking.population_size,
        ),
        attend=_hypothesis(attend, current),
        not_attend=_hypothesis(not_attend, current),
        position_estimate=estimate,
    )

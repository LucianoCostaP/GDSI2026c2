"""Simulador de puntaje por asistencia (HU-18, `docs/contrato-api-simulador.md`).

Simula un solo evento sobre la instantánea que guardó el último ranking completado: no combina
otros próximos eventos (escenario 1) y no guarda nada (FR-004). Los puntajes salen del motor
único (`scoring.engine.calculate_score`) con las reglas de ese ranking.

Un evento que no está publicado o que ya empezó no se simula (escenario 3). Si el club publicó
reglas nuevas después del ranking, la simulación sigue usando las del ranking y lo avisa
(escenario 8).

Pendiente (próximos escenarios): distancia actual (9) y posición estimada (10). Mientras tanto la posición de un Partido no se estima, que es lo
que corresponde con `position_projection_enabled` apagado (su valor por defecto).
"""

import uuid
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.date_utils import asegurar_utc, formatear_tipo_evento
from ..core.exceptions import PasioDe10Exception
from ..models import (
    EstadoCuota,
    EventoPendienteDB,
    EventoVisibleDB,
    Ranking,
    RankingEntry,
    RulesVersion,
    User,
    utcnow,
)
from ..models.enums import TipoEvento
from ..schemas.simulator import (
    CurrentStandingOut,
    HypothesisOut,
    PositionEstimateOut,
    RulesNoticeOut,
    SimulatedEventOut,
    SimulationOut,
    SimulationRankingOut,
    SimulatorStatusOut,
)
from ..scoring.attendance_inputs import MATCH_CLASSES
from ..scoring.engine import ScoringInputs, ScoringParameters, calculate_score
from ..scoring.snapshot import scoring_inputs_from_snapshot
from .formula_service import get_in_force
from .ranking_service import _socio_of, get_ranking_in_force

EVENT_NOT_FOUND_MESSAGE = "No encontramos el evento."
EVENT_NOT_SIMULABLE_MESSAGE = "Este evento ya no está disponible para simular."
NOT_IN_RANKING_MESSAGE = (
    "Para simular necesitás un puntaje calculado. Todavía no estás en el ranking."
)
POSITION_NOT_AVAILABLE_MESSAGE = (
    "No podemos estimar tu posición en este momento. Te mostramos solo tu puntaje."
)
RULES_AHEAD_MESSAGE = (
    "Esta simulación usa las reglas del último ranking (versión {n}). Las reglas vigentes "
    "se aplicarán desde el próximo cálculo."
)
INSTITUTIONAL_NOTICE = (
    "No asistir no cambia tu puntaje, pero tu posición puede bajar si otros socios "
    "suman puntos."
)


def _not_simulable() -> PasioDe10Exception:
    return PasioDe10Exception(
        EVENT_NOT_SIMULABLE_MESSAGE, status.HTTP_409_CONFLICT, "EVENT_NOT_SIMULABLE"
    )


def _simulable_event(
    db: Session, club_id: uuid.UUID, event_id: str, now: datetime
) -> EventoVisibleDB:
    """El evento publicado y todavía no empezado del club (escenario 3, FR-001).

    Uno de otro club responde igual que uno inexistente (FR-009). Uno del club que todavía no
    está publicado, o que ya empezó, se rechaza sin calcular nada.
    """
    event = db.scalar(
        select(EventoVisibleDB).where(
            EventoVisibleDB.id_interno == event_id,
            EventoVisibleDB.club_id == club_id,
        )
    )
    if event is None:
        pending = db.scalar(
            select(EventoPendienteDB.id_interno).where(
                EventoPendienteDB.id_interno == event_id,
                EventoPendienteDB.club_id == club_id,
            )
        )
        if pending is not None:
            raise _not_simulable()
        raise PasioDe10Exception(
            EVENT_NOT_FOUND_MESSAGE, status.HTTP_404_NOT_FOUND, "EVENT_NOT_FOUND"
        )
    if asegurar_utc(event.fecha_hora) <= now:
        raise _not_simulable()
    is_match = event.tipo == TipoEvento.PARTIDO.value
    if (is_match and event.clase not in MATCH_CLASSES) or (
        not is_match
        and (event.tipo != TipoEvento.INSTITUCIONAL.value or not event.puntos)
    ):
        # Un Partido sin clase o un institucional sin puntos no entran en el cálculo.
        raise _not_simulable()
    return event


def _ranked_entry(
    db: Session, member_user: User, club_id: uuid.UUID
) -> tuple[Ranking, RankingEntry] | None:
    """El ranking vigente y la entrada del socio en él, o `None` si no puede simular.

    Cubre todos los casos del escenario 2: no hay ranking completado, la cuenta no tiene socio
    en el padrón, la cuota está vencida (se lee del padrón en el momento, como en HU-14) o el
    socio no tiene entrada (ingresó después del cálculo).
    """
    ranking = get_ranking_in_force(db, club_id)
    socio = _socio_of(db, member_user, club_id)
    if (
        ranking is None
        or socio is None
        or socio.estado_cuota != EstadoCuota.AL_DIA.value
    ):
        return None
    entry = db.scalar(
        select(RankingEntry).where(
            RankingEntry.ranking_id == ranking.id, RankingEntry.socio_id == socio.id
        )
    )
    return None if entry is None else (ranking, entry)


def _ranking_out(db: Session, ranking: Ranking) -> SimulationRankingOut:
    rules_number = db.scalar(
        select(RulesVersion.number).where(RulesVersion.id == ranking.rules_version_id)
    )
    assert rules_number is not None  # clave foránea
    return SimulationRankingOut(
        completed_at=ranking.completed_at,
        calculation_date=ranking.calculation_date,
        rules_version=rules_number,
    )


def _rules_notice(
    db: Session, club_id: uuid.UUID, ranking_rules: RulesVersion
) -> RulesNoticeOut | None:
    """Aviso cuando las reglas vigentes del club ya no son las que usó el ranking."""
    in_force = get_in_force(db, club_id)
    if in_force is None or in_force.id == ranking_rules.id:
        return None
    return RulesNoticeOut(
        code="RULES_AHEAD_OF_RANKING",
        message=RULES_AHEAD_MESSAGE.format(n=ranking_rules.number),
    )


def simulator_status(
    db: Session, member_user: User, club_id: uuid.UUID
) -> SimulatorStatusOut:
    """HU-18, escenario 2: si el socio puede simular. Nunca es un error."""
    ranked = _ranked_entry(db, member_user, club_id)
    if ranked is None:
        return SimulatorStatusOut(
            status="unavailable",
            reason="NOT_IN_RANKING",
            message=NOT_IN_RANKING_MESSAGE,
            ranking=None,
        )
    return SimulatorStatusOut(
        status="available",
        reason=None,
        message=None,
        ranking=_ranking_out(db, ranked[0]),
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
    db: Session,
    member_user: User,
    club_id: uuid.UUID,
    event_id: str,
    now: datetime | None = None,
) -> SimulationOut:
    """HU-18: puntaje del socio si asiste y si no asiste a un evento, sin guardar nada."""
    event = _simulable_event(db, club_id, event_id, asegurar_utc(now or utcnow()))

    ranked = _ranked_entry(db, member_user, club_id)
    if ranked is None:
        raise PasioDe10Exception(
            NOT_IN_RANKING_MESSAGE, status.HTTP_409_CONFLICT, "NOT_IN_RANKING"
        )
    ranking, entry = ranked

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
        ranking=_ranking_out(db, ranking),
        rules_notice=_rules_notice(db, club_id, rules),
        current=CurrentStandingOut(
            score=f"{current:.2f}",
            position=entry.position,
            ranked_total=ranking.population_size,
        ),
        attend=_hypothesis(attend, current),
        not_attend=_hypothesis(not_attend, current),
        position_estimate=estimate,
    )

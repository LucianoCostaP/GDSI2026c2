"""Simulador de puntaje por asistencia (HU-18, `docs/contrato-api-simulador.md`).

Simula un solo evento sobre la instantánea que guardó el último ranking completado: no combina
otros próximos eventos (escenario 1) y no guarda nada (FR-004). Los puntajes salen del motor
único (`scoring.engine.calculate_score`) con las reglas de ese ranking.

Un evento que no está publicado o que ya empezó no se simula (escenario 3). Si el club publicó
reglas nuevas después del ranking, la simulación sigue usando las del ranking y lo avisa
(escenario 8). Las proyecciones usan la distancia actual del socio en el padrón; el puntaje y la
posición actuales quedan los del ranking, así que la diferencia incluye el cambio de distancia
(escenario 9).

Para un Partido, si el club tiene encendida `position_projection_enabled`, cada hipótesis trae
un puesto estimado con su rango probable (escenario 10, `scoring.position`). Los otros socios se
toman tal como los tiene el ranking: sus dos totales para el evento salen del mismo motor.
"""

import logging
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.date_utils import asegurar_utc, formatear_tipo_evento
from ..core.exceptions import PasioDe10Exception
from ..models import (
    Club,
    EstadoCuota,
    EventoPendienteDB,
    EventoVisibleDB,
    Ranking,
    RankingEntry,
    RulesVersion,
    Socio,
    User,
    utcnow,
)
from ..models.enums import TipoEvento
from ..schemas.simulator import (
    CurrentStandingOut,
    DistanceOut,
    EstimatedPositionOut,
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
from ..scoring.position import (
    OtherOutcome,
    PositionRange,
    attendance_probability,
    club_rate,
    estimate_position,
    z_for_level,
)
from ..scoring.ranking_order import RankingCandidate, ranks_above
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
DISTANCE_CHANGED_MESSAGE = (
    "Tu distancia al estadio cambió desde el último ranking: la simulación usa {nuevo} km "
    "y tu puntaje de hoy usa {anterior} km."
)
ESTIMATE_LABEL = (
    "Estimación: supone que cada socio asiste según su propio historial. Puede diferir "
    "después del próximo cálculo."
)
INSTITUTIONAL_NOTICE = (
    "No asistir no cambia tu puntaje, pero tu posición puede bajar si otros socios "
    "suman puntos."
)

logger = logging.getLogger(__name__)


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
) -> tuple[Ranking, RankingEntry, Socio] | None:
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
    return None if entry is None else (ranking, entry, socio)


def _km_text(km: Decimal) -> str:
    """Distancia para el aviso: sin decimales de más y con coma decimal (es-AR)."""
    text = f"{km.normalize():f}"
    return text.replace(".", ",")


def _distance(socio: Socio, ranking_km: Decimal) -> DistanceOut:
    """Distancia actual del padrón contra la del ranking (escenario 9, FR-011).

    Solo se refresca la del propio socio. Si no hubiera un registro actual, se usa la del
    ranking (caso borde "Change of home").
    """
    used_km = socio.distancia_km if socio.distancia_km is not None else ranking_km
    changed = used_km != ranking_km
    notice = (
        DISTANCE_CHANGED_MESSAGE.format(
            nuevo=_km_text(used_km), anterior=_km_text(ranking_km)
        )
        if changed
        else None
    )
    return DistanceOut(
        used_km=f"{used_km:.2f}",
        ranking_km=f"{ranking_km:.2f}",
        changed=changed,
        notice=notice,
    )


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


def _hypothesis(
    score: Decimal, current: Decimal, position: PositionRange | None = None
) -> HypothesisOut:
    return HypothesisOut(
        score=f"{score:.2f}",
        difference=f"{score - current:.2f}",
        position=None if position is None else _position_out(position),
    )


@dataclass(frozen=True)
class _Other:
    """Otro socio del ranking, con sus dos totales para el Partido."""

    attends: RankingCandidate
    skips: RankingCandidate
    attended: int
    counted: int


class _NotEstimated(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _position_out(position: PositionRange) -> EstimatedPositionOut:
    text = f"puesto estimado {_thousands(position.estimate)}"
    if position.lower != position.upper:
        text += (
            f" (probable entre {_thousands(position.lower)} y "
            f"{_thousands(position.upper)})"
        )
    return EstimatedPositionOut(
        estimate=position.estimate,
        lower=position.lower,
        upper=position.upper,
        text=text,
    )


def _candidate(
    socio_id: uuid.UUID, total: Decimal, inputs: dict, dni: str
) -> RankingCandidate:
    membership = inputs["membership"]
    return RankingCandidate(
        socio_id=socio_id,
        total=total,
        seniority_start=date.fromisoformat(membership["seniority_start"]),
        birth_date=date.fromisoformat(membership["birth_date"]),
        dni=dni,
    )


def _estimated_positions(
    db: Session,
    club: Club,
    ranking: Ranking,
    params: ScoringParameters,
    event: EventoVisibleDB,
    entry: RankingEntry,
    socio: Socio,
    totals: tuple[Decimal, Decimal],
) -> tuple[PositionRange, PositionRange]:
    """Puesto estimado si asiste y si no asiste ("Position model").

    Lanza `_NotEstimated` con el motivo cuando la posición no se estima.
    """
    rows = db.execute(
        select(RankingEntry.socio_id, RankingEntry.inputs, Socio.dni)
        .join(Socio, Socio.id == RankingEntry.socio_id)
        .where(RankingEntry.ranking_id == ranking.id)
    ).all()
    match_class = str(event.clase)
    rate = club_rate(
        (
            (
                row.inputs["attendance"]["attended_by_class"],
                row.inputs["attendance"]["matches_by_class"],
            )
            for row in rows
        ),
        match_class,
    )
    if rate is None:
        raise _NotEstimated("INSUFFICIENT_HISTORY")
    if ranking.population_size < club.position_min_population:
        raise _NotEstimated("SMALL_POPULATION")

    others: list[_Other] = []
    for row in rows:
        if row.socio_id == entry.socio_id:
            continue
        inputs = scoring_inputs_from_snapshot(row.inputs)
        attends = calculate_score(
            _with_event(inputs, event, attends=True), params
        ).total
        skips = calculate_score(_with_event(inputs, event, attends=False), params).total
        others.append(
            _Other(
                attends=_candidate(row.socio_id, attends, row.inputs, row.dni),
                skips=_candidate(row.socio_id, skips, row.inputs, row.dni),
                attended=inputs.attended_by_class.get(match_class, 0),
                counted=inputs.matches_by_class.get(match_class, 0),
            )
        )

    z = z_for_level(club.position_range_level)

    def position_for(total: Decimal) -> PositionRange:
        own = _candidate(socio.id, total, entry.inputs, socio.dni)
        outcomes = [
            OtherOutcome(
                probability=attendance_probability(
                    other.attended, other.counted, rate, club.position_prior_strength
                ),
                above_if_attends=ranks_above(other.attends, own),
                above_if_skips=ranks_above(other.skips, own),
            )
            for other in others
        ]
        return estimate_position(outcomes, ranking.population_size, z)

    attend_total, not_attend_total = totals
    return position_for(attend_total), position_for(not_attend_total)


def _match_position(
    db: Session,
    club_id: uuid.UUID,
    ranking: Ranking,
    params: ScoringParameters,
    event: EventoVisibleDB,
    entry: RankingEntry,
    socio: Socio,
    totals: tuple[Decimal, Decimal],
) -> tuple[PositionEstimateOut, PositionRange | None, PositionRange | None]:
    """La posición estimada de un Partido, o el motivo (como código) de por qué no hay."""
    club = db.get(Club, club_id)
    assert club is not None  # el club de la cuenta
    reason = "PROJECTION_DISABLED"
    if club.position_projection_enabled:
        try:
            attend, not_attend = _estimated_positions(
                db, club, ranking, params, event, entry, socio, totals
            )
        except _NotEstimated as not_estimated:
            reason = not_estimated.reason
        except Exception:
            # La posición es secundaria: si falla, se muestran solo los puntajes.
            logger.exception("Falló la posición estimada del ranking %s", ranking.id)
            reason = "POSITION_ERROR"
        else:
            estimate = PositionEstimateOut(
                status="estimated",
                code=None,
                reason=None,
                message=None,
                label=ESTIMATE_LABEL,
                range_level=f"{club.position_range_level:.2f}",
            )
            return estimate, attend, not_attend
    unavailable = PositionEstimateOut(
        status="unavailable",
        code="POSITION_NOT_AVAILABLE",
        reason=reason,
        message=POSITION_NOT_AVAILABLE_MESSAGE,
    )
    return unavailable, None, None


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
    ranking, entry, socio = ranked

    rules = db.get(RulesVersion, ranking.rules_version_id)
    assert rules is not None  # clave foránea
    params = ScoringParameters.from_values(rules.values)
    snapshot = scoring_inputs_from_snapshot(entry.inputs)
    distance = _distance(socio, snapshot.distance_km)
    base = replace(snapshot, distance_km=Decimal(distance.used_km))
    current = entry.total
    attend = calculate_score(_with_event(base, event, attends=True), params).total
    not_attend = calculate_score(_with_event(base, event, attends=False), params).total

    is_match = event.tipo == TipoEvento.PARTIDO.value
    attend_position: PositionRange | None = None
    not_attend_position: PositionRange | None = None
    if is_match:
        estimate, attend_position, not_attend_position = _match_position(
            db, club_id, ranking, params, event, entry, socio, (attend, not_attend)
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
        distance=distance,
        current=CurrentStandingOut(
            score=f"{current:.2f}",
            position=entry.position,
            ranked_total=ranking.population_size,
        ),
        attend=_hypothesis(attend, current, attend_position),
        not_attend=_hypothesis(not_attend, current, not_attend_position),
        position_estimate=estimate,
    )

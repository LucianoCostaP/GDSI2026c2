"""Consultas sobre el ranking y desglose de puntaje del socio (HU-16 y HU-25).

El ranking vigente de un club es su última corrida completada (`status = completed`), la de
`completed_at` más reciente: ese momento es "desde cuándo rige" (FR-004). Una corrida en curso
o fallida nunca es vigente, así que los Socios nunca ven una (FR-010). Las corridas anteriores
se conservan en la base, pero no se exponen (el historial queda fuera del MVP).

El reemplazo es atómico porque la corrida guarda sus entradas y pasa a `completed` en una sola
transacción (ver `ranking_run_service`): hasta que esa transacción se confirma, el ranking
vigente sigue siendo el anterior.

Este módulo no importa a `ranking_run_service`: `formula_service` lo importa a él.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Member,
    Ranking,
    RankingEntry,
    RankingState,
    RulesVersion,
    Socio,
    User,
)
from ..schemas.ranking import ScoreBreakdownResponse, ScoreComponentOut

COMPONENT_NAMES: dict[str, str] = {
    "attendance_frequency": "asistencia – frecuencia",
    "attendance_distance": "asistencia – distancia",
    "institutional": "participación institucional",
    "seniority_age": "antigüedad y edad",
    "new_member_bonus": "bonus nuevo socio",
    "cap_adjustment": "ajuste por tope",
}

NO_RANKING_MESSAGE = (
    "Todavía no formás parte de un ranking completado. El desglose estará "
    "disponible una vez que se publique una corrida del ranking en la que estés incluido/a."
)

CAP_EXPLANATION = (
    "El puntaje total está topeado en 100 puntos. Se aplica un ajuste para absorber el "
    "excedente de la suma de los componentes."
)


def get_ranking_in_force(db: Session, club_id: uuid.UUID) -> Ranking | None:
    """El ranking vigente del club: su última corrida completada, o `None` si no tiene."""
    return db.scalar(
        select(Ranking)
        .where(Ranking.club_id == club_id, Ranking.status == RankingState.COMPLETED)
        .order_by(Ranking.completed_at.desc(), Ranking.id.desc())
        .limit(1)
    )


# Alias para compatibilidad con HU-16
latest_completed_ranking = get_ranking_in_force


def latest_completed_ranking_rules_number(
    db: Session, club_id: uuid.UUID
) -> int | None:
    """Número de la versión de reglas que usó el último ranking completado del club, o
    `None` si el club todavía no tiene ninguno."""
    ranking = get_ranking_in_force(db, club_id)
    if ranking is None:
        return None
    return db.scalar(
        select(RulesVersion.number).where(RulesVersion.id == ranking.rules_version_id)
    )


def _find_socio_for_user(
    db: Session, member_user: User, club_id: uuid.UUID
) -> Socio | None:
    """Encuentra el registro de `Socio` correspondiente al usuario autenticado."""
    if member_user.member_id:
        socio = db.scalars(
            select(Socio).where(
                Socio.club_id == club_id,
                Socio.numero_socio == member_user.member_id,
            )
        ).first()
        if socio:
            return socio

    member = db.get(Member, member_user.member_id)
    if member and member.dni:
        return db.scalars(
            select(Socio).where(
                Socio.club_id == club_id,
                Socio.dni == member.dni,
            )
        ).first()

    return None


def _format_two_decimals(val: Decimal | float | str | None) -> str:
    if val is None:
        return "0.00"
    dec = Decimal(str(val))
    return f"{dec:.2f}"


def get_member_score_breakdown(
    db: Session,
    member_user: User,
    club_id: uuid.UUID,
) -> ScoreBreakdownResponse:
    """Devuelve el desglose oficial de componentes del puntaje de un socio (HU-16)."""
    socio = _find_socio_for_user(db, member_user, club_id)
    if socio is None:
        return ScoreBreakdownResponse(
            has_ranking=False,
            message=NO_RANKING_MESSAGE,
        )

    ranking = latest_completed_ranking(db, club_id)
    if ranking is None:
        return ScoreBreakdownResponse(
            has_ranking=False,
            message=NO_RANKING_MESSAGE,
        )

    entry = db.scalars(
        select(RankingEntry).where(
            RankingEntry.ranking_id == ranking.id,
            RankingEntry.socio_id == socio.id,
        )
    ).first()
    if entry is None:
        return ScoreBreakdownResponse(
            has_ranking=False,
            message=NO_RANKING_MESSAGE,
        )

    rules_version = db.get(RulesVersion, ranking.rules_version_id)
    rules_version_number = rules_version.number if rules_version else None

    inputs = entry.inputs or {}
    att_in = inputs.get("attendance", {})
    inst_in = inputs.get("institutional", {})
    memb_in = inputs.get("membership", {})

    matches_by_class = dict(att_in.get("matches_by_class", {"A": 0, "B": 0, "C": 0}))
    attended_by_class = dict(att_in.get("attended_by_class", {"A": 0, "B": 0, "C": 0}))
    total_matches = sum(matches_by_class.values())
    total_attended = sum(attended_by_class.values())

    raw_event_points = inst_in.get("event_points", 0)
    raw_activity_points = inst_in.get("activity_points", 0)
    total_inst_raw = raw_event_points + raw_activity_points

    unadjusted_sum = (
        Decimal(str(entry.attendance_frequency))
        + Decimal(str(entry.attendance_distance))
        + Decimal(str(entry.institutional))
        + Decimal(str(entry.seniority_age))
        + Decimal(str(entry.new_member_bonus))
    )

    cap_adj = Decimal(str(entry.cap_adjustment))
    cap_explanation = CAP_EXPLANATION if cap_adj < 0 else None

    components: list[ScoreComponentOut] = [
        ScoreComponentOut(
            key="attendance_frequency",
            name=COMPONENT_NAMES["attendance_frequency"],
            points=_format_two_decimals(entry.attendance_frequency),
            supporting_figures={
                "matches_by_class": matches_by_class,
                "attended_by_class": attended_by_class,
                "total_matches": total_matches,
                "total_attended": total_attended,
                "effective_start": att_in.get("effective_start"),
            },
        ),
        ScoreComponentOut(
            key="attendance_distance",
            name=COMPONENT_NAMES["attendance_distance"],
            points=_format_two_decimals(entry.attendance_distance),
            supporting_figures={
                "distance_km": att_in.get("distance_km", "0.0"),
                "attended_matches": att_in.get("attended_matches", total_attended),
            },
        ),
        ScoreComponentOut(
            key="institutional",
            name=COMPONENT_NAMES["institutional"],
            points=_format_two_decimals(entry.institutional),
            supporting_figures={
                "event_points": raw_event_points,
                "events_count": len(inst_in.get("events", [])),
                "activity_points": raw_activity_points,
                "activity_months": inst_in.get("activity_months", {}),
                "total_points_before_cap": total_inst_raw,
            },
        ),
        ScoreComponentOut(
            key="seniority_age",
            name=COMPONENT_NAMES["seniority_age"],
            points=_format_two_decimals(entry.seniority_age),
            supporting_figures={
                "seniority_years": memb_in.get("seniority_years", 0),
                "age_years": memb_in.get("age_years", 0),
                "seniority_start": memb_in.get("seniority_start"),
            },
        ),
        ScoreComponentOut(
            key="new_member_bonus",
            name=COMPONENT_NAMES["new_member_bonus"],
            points=_format_two_decimals(entry.new_member_bonus),
            supporting_figures={
                "days_since_alta": memb_in.get("days_since_alta", 0),
                "bonus_applied": bool(entry.new_member_bonus > 0),
            },
        ),
        ScoreComponentOut(
            key="cap_adjustment",
            name=COMPONENT_NAMES["cap_adjustment"],
            points=_format_two_decimals(entry.cap_adjustment),
            supporting_figures={
                "unadjusted_sum": _format_two_decimals(unadjusted_sum),
                "difference": _format_two_decimals(entry.cap_adjustment),
                "max_cap": "100.00",
            },
            explanation=cap_explanation,
        ),
    ]

    return ScoreBreakdownResponse(
        has_ranking=True,
        message=None,
        rules_version=rules_version_number,
        calculation_date=ranking.calculation_date,
        total=_format_two_decimals(entry.total),
        position=entry.position,
        components=components,
    )

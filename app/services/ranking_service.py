"""Consultas sobre el ranking vigente que usan otras historias (HU-25, Ciclo 6; HU-14).

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
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    EstadoCuota,
    Member,
    Ranking,
    RankingEntry,
    RankingState,
    RulesVersion,
    Socio,
    User,
)


def get_ranking_in_force(db: Session, club_id: uuid.UUID) -> Ranking | None:
    """El ranking vigente del club: su última corrida completada, o `None` si no tiene."""
    return db.scalar(
        select(Ranking)
        .where(Ranking.club_id == club_id, Ranking.status == RankingState.COMPLETED)
        .order_by(Ranking.completed_at.desc(), Ranking.id.desc())
        .limit(1)
    )


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


# --- HU-14: puntaje y posición del Socio ----------------------------------------------------

PROVISIONAL_LABEL = "Provisional: todavía no calculado"
NOT_IN_RANKING_MESSAGE = (
    "Todavía no estás en el ranking: vas a aparecer después del próximo cálculo."
)
NO_RANKING_MESSAGE = (
    "Todavía no hay un ranking disponible. Tu puntaje va a aparecer cuando el club "
    "calcule el primero."
)
FEES_OVERDUE_MESSAGE = (
    "El ranking solo incluye a los socios con la cuota al día. Tu historial de asistencia "
    "y participación se conserva para el próximo cálculo luego de regularizar tu cuota."
)
ZERO_SCORE = "0.00"


def _socio_of(db: Session, member_user: User, club_id: uuid.UUID) -> Socio | None:
    """El socio del padrón del club que corresponde a la cuenta: por club y documento, porque
    el documento solo es único dentro de cada club."""
    if member_user.member_id is None:
        return None
    member = db.get(Member, member_user.member_id)
    if member is None:
        return None
    return db.scalar(
        select(Socio).where(Socio.club_id == club_id, Socio.dni == member.dni)
    )


def member_standing(
    db: Session, member_user: User, club_id: uuid.UUID
) -> dict[str, Any]:
    """HU-14: puntaje, posición y datos del ranking vigente para el Socio.

    Nunca es un error: si no hay datos responde la vista provisional. La cuota se lee del
    padrón en el momento (la misma que define la población de HU-25), así que un moroso ve la
    vista de cuotas vencidas aunque tenga entrada en el ranking vigente (escenario 5).
    """
    ranking = get_ranking_in_force(db, club_id)
    socio = _socio_of(db, member_user, club_id)

    ranked_total = ranking.population_size if ranking is not None else 0
    ranking_out = None
    if ranking is not None:
        ranking_out = {
            "completed_at": ranking.completed_at,
            "rules_version": db.scalar(
                select(RulesVersion.number).where(
                    RulesVersion.id == ranking.rules_version_id
                )
            ),
        }

    def provisional(reason: str, message: str) -> dict[str, Any]:
        return {
            "status": "provisional",
            "reason": reason,
            "score": ZERO_SCORE,
            # El final del ranking (N de N): solo de pantalla, no se guarda.
            "position": ranked_total or None,
            "ranked_total": ranked_total,
            "ranking": ranking_out,
            "label": PROVISIONAL_LABEL,
            "message": message,
        }

    if socio is not None and socio.estado_cuota != EstadoCuota.AL_DIA.value:
        return provisional("FEES_OVERDUE", FEES_OVERDUE_MESSAGE)
    if not ranked_total:
        return provisional("NO_RANKING", NO_RANKING_MESSAGE)

    assert ranking is not None
    entry = (
        db.scalar(
            select(RankingEntry).where(
                RankingEntry.ranking_id == ranking.id,
                RankingEntry.socio_id == socio.id,
            )
        )
        if socio is not None
        else None
    )
    if entry is None:
        return provisional("NOT_IN_RANKING", NOT_IN_RANKING_MESSAGE)
    return {
        "status": "ranked",
        "reason": None,
        "score": f"{entry.total:.2f}",
        "position": entry.position,
        "ranked_total": ranked_total,
        "ranking": ranking_out,
        "label": None,
        "message": None,
    }

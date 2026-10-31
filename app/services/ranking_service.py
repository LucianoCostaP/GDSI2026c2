"""Consultas sobre el ranking vigente que usan otras historias (HU-25, Ciclo 6).

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

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Ranking, RankingState, RulesVersion


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
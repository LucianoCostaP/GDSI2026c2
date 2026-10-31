"""Cálculo del ranking de socios (HU-25).

El club sale siempre de la cuenta del Admin (decisión 34): este endpoint no lee `club_id`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..auth import CurrentAdmin, CurrentAdminClub
from ..db import get_db
from ..models import Ranking, RankingState, RulesVersion, utcnow
from ..schemas.ranking import RankingRunOut
from ..services import ranking_run_service
from ..services.formula_service import error

router = APIRouter(prefix="/admin/ranking", tags=["admin ranking"])

Db = Annotated[Session, Depends(get_db)]


def _run_out(db: Session, ranking: Ranking) -> RankingRunOut:
    rules = db.get_one(RulesVersion, ranking.rules_version_id)
    return RankingRunOut(
        id=ranking.id,
        status=ranking.status,
        rules_version=rules.number,
        calculation_date=ranking.calculation_date,
        calculated_at=ranking.calculated_at,
        completed_at=ranking.completed_at,
        population_size=ranking.population_size,
        error=(
            ranking_run_service.RUN_FAILED_MESSAGE
            if ranking.status == RankingState.FAILED
            else None
        )
    )


@router.post("/runs", status_code=status.HTTP_201_CREATED)
def start_ranking_run(
    admin: CurrentAdmin, club_id: CurrentAdminClub, db: Db
) -> RankingRunOut:
    """Calcula el ranking. Responde 409 `RANKING_RUN_IN_PROGRESS` si ya hay uno en curso."""
    return _run_out(db, ranking_run_service.start_run(db, admin, club_id))


@router.get("/runs/latest")
def latest_ranking_run(club_id: CurrentAdminClub, db: Db) -> RankingRunOut:
    """Estado de la corrida más reciente: `running` mientras se calcula, luego `completed`
    (con `completed_at`: desde cuándo rige) o `failed`."""
    # Una corrida en curso de más de 15 minutos se da por abandonada antes de informarla.
    ranking_run_service.fail_abandoned_runs(db, club_id, utcnow())
    ranking = ranking_run_service.get_latest_run(db, club_id)
    if ranking is None:
        raise error(
            status.HTTP_404_NOT_FOUND,
            ranking_run_service.NO_RANKING_RUN,
            "Todavía no se calculó ningún ranking.",
        )
    return _run_out(db, ranking)
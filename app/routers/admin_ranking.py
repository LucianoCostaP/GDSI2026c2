"""Cálculo del ranking de socios (HU-25).

El club sale siempre de la cuenta del Admin (decisión 34): este endpoint no lee `club_id`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..auth import CurrentAdmin, CurrentAdminClub
from ..db import get_db
from ..models import RulesVersion
from ..schemas.ranking import RankingRunOut
from ..services import ranking_run_service

router = APIRouter(prefix="/admin/ranking", tags=["admin ranking"])

Db = Annotated[Session, Depends(get_db)]


@router.post("/runs", status_code=status.HTTP_201_CREATED)
def start_ranking_run(
    admin: CurrentAdmin, club_id: CurrentAdminClub, db: Db
) -> RankingRunOut:
    ranking = ranking_run_service.start_run(db, admin, club_id)
    rules = db.get_one(RulesVersion, ranking.rules_version_id)
    return RankingRunOut(
        id=ranking.id,
        status=ranking.status,
        rules_version=rules.number,
        calculation_date=ranking.calculation_date,
        calculated_at=ranking.calculated_at,
        completed_at=ranking.completed_at,
        population_size=ranking.population_size,
    )
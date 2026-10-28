"""Explicación del ranking para el Socio (HU-13).

El club sale siempre de la cuenta del Socio (decisión 34): este endpoint no lee `club_id` ni
`X-Club-ID`, aunque lleguen. Una sola ruta, sin alias.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..auth import CurrentMember, CurrentMemberClub
from ..db import get_db
from ..services import formula_service

router = APIRouter(prefix="/member/scoring", tags=["member scoring"])

Db = Annotated[Session, Depends(get_db)]


@router.get("/explanation")
def ranking_explanation(
    _: CurrentMember, club_id: CurrentMemberClub, db: Db, response: Response
) -> dict[str, Any]:
    # Siempre las reglas vigentes: nada de copias en caché (escenario 3).
    response.headers["Cache-Control"] = "no-store"
    return formula_service.member_explanation(db, club_id)

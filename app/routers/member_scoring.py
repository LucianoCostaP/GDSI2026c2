"""Explicación del ranking (HU-13), puntaje y posición (HU-14), desglose (HU-16) y simulador
(HU-18) del Socio.

El club sale siempre de la cuenta del Socio (decisión 34): estos endpoints no leen `club_id` ni
`X-Club-ID`, aunque lleguen. Una sola ruta, sin alias.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..auth import CurrentMember, CurrentMemberClub
from ..db import get_db
from ..schemas.ranking import ScoreBreakdownResponse
from ..schemas.simulator import SimulationOut, SimulatorStatusOut
from ..services import formula_service, ranking_service, simulator_service

router = APIRouter(prefix="/member/scoring", tags=["member scoring"])

Db = Annotated[Session, Depends(get_db)]


@router.get("/explanation")
def ranking_explanation(
    _: CurrentMember, club_id: CurrentMemberClub, db: Db, response: Response
) -> dict[str, Any]:
    # Siempre las reglas vigentes: nada de copias en caché (escenario 3).
    response.headers["Cache-Control"] = "no-store"
    return formula_service.member_explanation(db, club_id)


@router.get("/current")
def current_score_and_position(
    member: CurrentMember, club_id: CurrentMemberClub, db: Db, response: Response
) -> dict[str, Any]:
    """Solo lectura: siempre responde 200, con la vista provisional si no hay datos."""
    response.headers["Cache-Control"] = "no-store"
    return ranking_service.member_standing(db, member, club_id)


@router.get("/breakdown", response_model=ScoreBreakdownResponse)
def score_breakdown(
    member: CurrentMember, club_id: CurrentMemberClub, db: Db, response: Response
) -> ScoreBreakdownResponse:
    """Desglose de componentes del puntaje del socio (HU-16)."""
    response.headers["Cache-Control"] = "no-store"
    return ranking_service.get_member_score_breakdown(db, member, club_id)


@router.get("/simulator", response_model=SimulatorStatusOut)
def simulator_status(
    member: CurrentMember, club_id: CurrentMemberClub, db: Db, response: Response
) -> SimulatorStatusOut:
    """HU-18: al abrir el simulador, si el socio puede simular. Siempre responde 200."""
    response.headers["Cache-Control"] = "no-store"
    return simulator_service.simulator_status(db, member, club_id)


@router.get("/simulator/{event_id}", response_model=SimulationOut)
def simulate_event(
    event_id: str,
    member: CurrentMember,
    club_id: CurrentMemberClub,
    db: Db,
    response: Response,
) -> SimulationOut:
    """HU-18: simulación de un evento, solo lectura (no guarda nada)."""
    response.headers["Cache-Control"] = "no-store"
    return simulator_service.simulate_event(db, member, club_id, event_id)

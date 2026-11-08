"""Simulación del impacto de un cambio de reglas (HU-29).

El club sale siempre de la cuenta del Admin (decisión 34): estos endpoints no leen `club_id`.
Nada se guarda: las respuestas llevan `Cache-Control: no-store`.
Contrato con el front: `docs/contrato-api-simulacion-reglas.md`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..auth import CurrentAdmin, CurrentAdminClub
from ..db import get_db
from ..schemas.rules_simulation import RulesSimulationFormOut
from ..services import rules_simulation_service

router = APIRouter(prefix="/admin/rules-simulation", tags=["admin rules simulation"])

Db = Annotated[Session, Depends(get_db)]


@router.get("", response_model=RulesSimulationFormOut)
def open_simulator(
    _: CurrentAdmin, club_id: CurrentAdminClub, db: Db, response: Response
) -> RulesSimulationFormOut:
    """Abrir el simulador: ranking base, formulario precargado con sus reglas y derivados.

    Responde `409 NO_BASELINE` si el club no tiene ningún ranking completado.
    """
    response.headers["Cache-Control"] = "no-store"
    return rules_simulation_service.simulator_form(db, club_id)

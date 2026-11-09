"""Simulación del impacto de un cambio de reglas (HU-29).

El club sale siempre de la cuenta del Admin (decisión 34): estos endpoints no leen `club_id`.
Nada se guarda: las respuestas llevan `Cache-Control: no-store`. No hay ningún endpoint para
aplicar los valores (escenario 25): eso se hace en HU-28.
Contrato con el front: `docs/contrato-api-simulacion-reglas.md`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..auth import CurrentAdmin, CurrentAdminClub
from ..db import get_db
from ..schemas.rules_simulation import (
    BreakdownOut,
    BreakdownRequest,
    ExportRequest,
    RulesSimulationFormOut,
    RulesSimulationResultOut,
    SimulationRequest,
)
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


@router.post("", response_model=RulesSimulationResultOut)
def run_simulation(
    body: SimulationRequest,
    _: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Db,
    response: Response,
) -> RulesSimulationResultOut:
    """Simular los valores hipotéticos contra el último ranking completado. No guarda nada.

    Responde `409 NO_BASELINE` sin ranking completado y `409 EMPTY_RANKING` si no tiene socios.
    """
    response.headers["Cache-Control"] = "no-store"
    return rules_simulation_service.simulate(db, club_id, body.values)


@router.post("/breakdown", response_model=BreakdownOut)
def run_breakdown(
    body: BreakdownRequest,
    _: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Db,
    response: Response,
) -> BreakdownOut:
    """Efecto de cada factor por separado, pedido después del resultado principal.

    Lleva los mismos valores y el `ranking_id` de ese resultado. Responde
    `409 BASELINE_NOT_FOUND` si ese ranking ya no es un ranking completado del club.
    """
    response.headers["Cache-Control"] = "no-store"
    return rules_simulation_service.breakdown(db, club_id, body.ranking_id, body.values)


@router.post("/export", response_class=Response)
def export_csv(
    body: ExportRequest,
    _: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Db,
) -> Response:
    """CSV con las cifras de la pantalla, generado en el momento; no se guarda.

    Lleva los mismos valores y el `ranking_id` del resultado principal. Errores en JSON, los
    mismos de `breakdown`.
    """
    name, content = rules_simulation_service.export(
        db, club_id, body.ranking_id, body.values
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )

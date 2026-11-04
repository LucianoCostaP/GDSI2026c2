"""Configuración del simulador de asistencia del club (HU-18, FR-010).

El club sale siempre de la cuenta del Admin (decisión 34): estos endpoints no leen `club_id`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import CurrentAdmin, CurrentAdminClub
from ..db import get_db
from ..schemas.simulator import SimulatorSettingsOut, SimulatorSettingsUpdate
from ..services import simulator_settings_service

router = APIRouter(prefix="/admin/simulator", tags=["admin simulator"])

Db = Annotated[Session, Depends(get_db)]


@router.get("/settings", response_model=SimulatorSettingsOut)
def get_settings(
    _: CurrentAdmin, club_id: CurrentAdminClub, db: Db
) -> SimulatorSettingsOut:
    return simulator_settings_service.get_settings(db, club_id)


@router.patch("/settings", response_model=SimulatorSettingsOut)
def update_settings(
    body: SimulatorSettingsUpdate,
    admin: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Db,
) -> SimulatorSettingsOut:
    """Cambia solo los campos enviados; la próxima simulación ya los usa."""
    return simulator_settings_service.update_settings(db, admin, club_id, body)

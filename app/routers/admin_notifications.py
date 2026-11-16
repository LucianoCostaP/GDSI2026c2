"""Trabajos de notificaciones a pedido del Admin (HU-19).

No hay scheduler (Render corre un solo servicio `web`): como `POST /admin/events/auto-publish`
de HU-22, el Admin corre a mano el trabajo de apertura de olas. Solo procesa los cronogramas de
su club (decisión 34).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import CurrentAdmin, CurrentAdminClub
from ..db import get_db
from ..notifications import generators
from .admin_events import _parse_clock

router = APIRouter(prefix="/admin/notifications", tags=["admin notifications"])

Db = Annotated[Session, Depends(get_db)]


class WaveOpeningsRunOut(BaseModel):
    created: int = Field(
        description="Notificaciones `wave_opened` creadas en esta corrida"
    )


@router.post("/wave-openings/run", response_model=WaveOpeningsRunOut)
def run_wave_openings(
    _: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Db,
    reloj_simulado: str | None = Query(
        None,
        description="Reloj simulado para pruebas (formato ISO); se ignora en producción",
    ),
) -> WaveOpeningsRunOut:
    created = generators.open_waves(
        db, now=_parse_clock(reloj_simulado), club_id=club_id
    )
    return WaveOpeningsRunOut(created=created)

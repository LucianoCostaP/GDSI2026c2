"""Advertencias antes de calcular el ranking (HU-25, Ciclo 8; FR-011, HU-43 FR-008).

Solo lee: no crea ni cambia nada. Las advertencias no bloquean el cálculo, el Admin decide si
continúa. Son tres, siempre en este orden:

- `ROSTER_STALE`: el padrón tiene más de `freshness_hours_limit` horas (24 por defecto), o el
  club nunca cargó uno. Reusa la regla de HU-43.
- `ATTENDANCE_STALE`: la última carga de asistencia exitosa tiene más de
  `attendance_freshness_days` días (7 por defecto), o el club nunca cargó una.
- `LOADS_AFTER_LAST_RANKING`: hubo cargas exitosas (padrón, asistencias o actividades)
  después de que empezó a calcularse el ranking vigente: ese ranking no las refleja. Sin
  ranking vigente no se emite.

Todos los límites son estrictos: un dato justo en el límite todavía está al día.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    CargaParticipacionDB,
    Club,
    EstadoCargaParticipacion,
    SocioCarga,
    TipoParticipacion,
)
from .carga_service import CargaService
from .ranking_service import get_ranking_in_force

ROSTER_STALE = "ROSTER_STALE"
ATTENDANCE_STALE = "ATTENDANCE_STALE"
LOADS_AFTER_LAST_RANKING = "LOADS_AFTER_LAST_RANKING"


@dataclass(frozen=True)
class PreflightWarning:
    code: str
    message: str
    # Fecha del dato que motiva la advertencia (`None` si el club nunca cargó ese dato).
    data_as_of: datetime | None


def _roster_warning(db: Session, club: Club, now: datetime) -> PreflightWarning | None:
    freshness = CargaService.obtener_frescura_padron(club, db, now=now)
    if not freshness.esta_desactualizado:
        return None
    return PreflightWarning(
        code=ROSTER_STALE,
        message=freshness.advertencia or "El padrón está desactualizado.",
        data_as_of=freshness.ultima_carga_exitosa,
    )


def _attendance_warning(
    db: Session, club: Club, now: datetime
) -> PreflightWarning | None:
    limit_days = settings.attendance_freshness_days
    last_load = db.scalar(
        select(func.max(CargaParticipacionDB.actualizado_en)).where(
            CargaParticipacionDB.club_id == club.id,
            CargaParticipacionDB.tipo == TipoParticipacion.ASISTENCIA.value,
            CargaParticipacionDB.estado == EstadoCargaParticipacion.SUCCESSFUL.value,
        )
    )
    if last_load is None:
        return PreflightWarning(
            code=ATTENDANCE_STALE,
            message=(
                "El club no tiene ninguna carga de asistencia exitosa. "
                f"Límite de antigüedad: {limit_days} días."
            ),
            data_as_of=None,
        )
    age = now - last_load
    if age <= timedelta(days=limit_days):
        return None
    return PreflightWarning(
        code=ATTENDANCE_STALE,
        message=(
            f"La última carga de asistencia tiene {age.days} días, "
            f"más que el límite de {limit_days} días."
        ),
        data_as_of=last_load,
    )


def _loads_after_ranking_warning(db: Session, club: Club) -> PreflightWarning | None:
    in_force = get_ranking_in_force(db, club.id)
    if in_force is None:
        return None
    since = in_force.calculated_at
    roster_load = db.scalar(
        select(func.max(SocioCarga.completado_en)).where(
            SocioCarga.club_id == club.id,
            SocioCarga.estado == "exitosa",
            SocioCarga.completado_en > since,
        )
    )
    participation_load = db.scalar(
        select(func.max(CargaParticipacionDB.actualizado_en)).where(
            CargaParticipacionDB.club_id == club.id,
            CargaParticipacionDB.estado == EstadoCargaParticipacion.SUCCESSFUL.value,
            CargaParticipacionDB.actualizado_en > since,
        )
    )
    latest = max(
        (load for load in (roster_load, participation_load) if load is not None),
        default=None,
    )
    if latest is None:
        return None
    return PreflightWarning(
        code=LOADS_AFTER_LAST_RANKING,
        message=(
            "Hubo cargas de datos después del último ranking: "
            "el ranking vigente no las refleja."
        ),
        data_as_of=latest,
    )


def build_preflight(db: Session, club: Club, now: datetime) -> list[PreflightWarning]:
    """Las advertencias que corresponden antes de calcular el ranking del club."""
    candidates = (
        _roster_warning(db, club, now),
        _attendance_warning(db, club, now),
        _loads_after_ranking_warning(db, club),
    )
    return [warning for warning in candidates if warning is not None]

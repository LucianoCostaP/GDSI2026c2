"""Configuración del simulador por club (HU-18 FR-010, cross-cutting §8).

La edita un Admin de su propio club (decisión 34). Cada cambio queda en la auditoría con los
valores anteriores y los nuevos.
"""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from ..audit import record
from ..models import Club, User
from ..schemas.simulator import SimulatorSettingsOut, SimulatorSettingsUpdate

FIELDS = (
    "position_projection_enabled",
    "position_range_level",
    "position_prior_strength",
    "position_min_population",
)


def _club(db: Session, club_id: uuid.UUID) -> Club:
    club = db.get(Club, club_id)
    assert club is not None  # el club de la cuenta
    return club


def _out(club: Club) -> SimulatorSettingsOut:
    return SimulatorSettingsOut(
        position_projection_enabled=club.position_projection_enabled,
        position_range_level=f"{club.position_range_level:.2f}",
        position_prior_strength=f"{club.position_prior_strength:.2f}",
        position_min_population=club.position_min_population,
    )


def _as_json(value: Any) -> Any:
    return value if isinstance(value, bool | int) else str(value)


def get_settings(db: Session, club_id: uuid.UUID) -> SimulatorSettingsOut:
    return _out(_club(db, club_id))


def update_settings(
    db: Session, admin: User, club_id: uuid.UUID, changes: SimulatorSettingsUpdate
) -> SimulatorSettingsOut:
    """Aplica los campos que llegaron; si nada cambia, no audita nada."""
    club = _club(db, club_id)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in FIELDS:
        value = getattr(changes, field)
        if value is None or value == getattr(club, field):
            continue
        before[field] = _as_json(getattr(club, field))
        after[field] = _as_json(value)
        setattr(club, field, value)
    if after:
        record(
            db,
            "simulator_settings.updated",
            actor_id=admin.id,
            entity="club",
            entity_id=str(club_id),
            club_id=str(club_id),
            before=before,
            after=after,
        )
        db.commit()
        db.refresh(club)
    return _out(club)

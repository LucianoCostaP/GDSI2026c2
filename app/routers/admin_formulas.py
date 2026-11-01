"""Fórmula base del club (HU-27): el Admin elige una del catálogo, la configura y la publica.

El club sale siempre de la cuenta del Admin (decisión 34): estos endpoints no leen `club_id`.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import CurrentAdmin, CurrentAdminClub
from ..db import get_db
from ..services import formula_service

router = APIRouter(prefix="/admin/formulas", tags=["admin formulas"])

Db = Annotated[Session, Depends(get_db)]


class ValuesRequest(BaseModel):
    values: dict[str, Any]


class PublishRequest(ValuesRequest):
    # Reglas vigentes cuando el Admin abrió la pantalla (`null` si no había ninguna).
    expected_rules_version: int | None
    confirmed: bool = False


class AdjustRequest(ValuesRequest):
    expected_rules_version: int
    confirmed: bool = False


class LockRequest(BaseModel):
    reason: str = Field(max_length=500)


@router.get("")
def list_formulas(_: CurrentAdmin, club_id: CurrentAdminClub, db: Db) -> dict[str, Any]:
    return formula_service.overview(db, club_id)


@router.post("/lock")
def lock_formula(
    body: LockRequest, admin: CurrentAdmin, club_id: CurrentAdminClub, db: Db
) -> dict[str, Any]:
    return formula_service.lock_formula(db, admin, club_id, body.reason)


@router.post("/unlock")
def unlock_formula(
    body: LockRequest, admin: CurrentAdmin, club_id: CurrentAdminClub, db: Db
) -> dict[str, Any]:
    return formula_service.unlock_formula(db, admin, club_id, body.reason)


@router.post("/adjust")
def adjust_parameters(
    body: AdjustRequest,
    admin: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Db,
) -> dict[str, Any]:
    return formula_service.adjust_parameters(
        db,
        admin,
        club_id,
        body.values,
        body.expected_rules_version,
        body.confirmed,
    )


@router.get("/{formula_id}/{version}")
def formula_detail(
    formula_id: str,
    version: int,
    _: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Db,
) -> dict[str, Any]:
    return formula_service.detail(db, club_id, formula_id, version)


@router.post("/{formula_id}/{version}/preview")
def preview_formula(
    formula_id: str,
    version: int,
    body: ValuesRequest,
    _: CurrentAdmin,
    __: CurrentAdminClub,
) -> dict[str, Any]:
    return formula_service.preview(formula_id, version, body.values)


@router.post("/{formula_id}/{version}/publish", status_code=status.HTTP_201_CREATED)
def publish_formula(
    formula_id: str,
    version: int,
    body: PublishRequest,
    admin: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Db,
) -> dict[str, Any]:
    return formula_service.publish(
        db,
        admin,
        club_id,
        formula_id,
        version,
        body.values,
        body.expected_rules_version,
        body.confirmed,
    )

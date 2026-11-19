"""Reportes ejecutivos para la administración (HU-42).

El club sale siempre de la cuenta del Admin (decisión 34): estos endpoints no leen `club_id`.
Nada se guarda ni se muta: las respuestas llevan `Cache-Control: no-store`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..auth import CurrentAdmin, CurrentAdminClub
from ..db import get_db
from ..schemas.executive_report import ExecutiveScoringReportOut
from ..services import executive_report_service

router = APIRouter(prefix="/admin/reports", tags=["admin reports"])

Db = Annotated[Session, Depends(get_db)]


@router.get(
    "/executive-scoring",
    response_model=ExecutiveScoringReportOut,
    summary="Reporte Ejecutivo de Scoring y Equidad (HU-42)",
)
def get_executive_scoring_report(
    admin: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Db,
    response: Response,
) -> ExecutiveScoringReportOut:
    """Genera el reporte ejecutivo de distribución de scoring y equidad sociodemográfica

    a partir del ranking vigente y completado del club.
    """
    response.headers["Cache-Control"] = "no-store"
    return executive_report_service.get_executive_scoring_report(
        db=db, club_id=club_id, admin_email=admin.email
    )


@router.get(
    "/executive-scoring/csv",
    summary="Exportar Reporte Ejecutivo de Scoring en formato CSV (HU-42)",
)
def export_executive_scoring_report_csv(
    admin: CurrentAdmin,
    club_id: CurrentAdminClub,
    db: Db,
) -> Response:
    """Descarga el reporte ejecutivo consolidado en formato CSV con codificación UTF-8 con BOM."""
    name, content = executive_report_service.export_executive_scoring_report_csv(
        db=db, club_id=club_id, admin_email=admin.email
    )
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )

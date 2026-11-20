"""Servicio del Reporte Ejecutivo de Scoring y Equidad (HU-42)."""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.domain import Club
from ..models.ranking import RankingEntry
from ..models.rules import RulesVersion
from ..schemas.executive_report import (
    ExecutiveReportMetadata,
    ExecutiveScoringReportOut,
    RulesVersionParametersOut,
)
from ..scoring.executive_report import (
    compute_executive_demographics,
    compute_executive_histogram,
    compute_executive_summary,
    compute_pillars_average,
    extract_executive_socios,
)
from .executive_report_export import (
    executive_report_csv_bytes,
    executive_report_filename,
)
from .ranking_service import get_ranking_in_force

NO_BASELINE_MESSAGE = "Todavía no hay un ranking calculado. Calculá el ranking para poder generar el reporte ejecutivo."
EMPTY_RANKING_MESSAGE = (
    "El ranking vigente no tiene socios: no hay datos para generar el reporte."
)


def get_executive_scoring_report(
    db: Session, club_id: uuid.UUID, admin_email: str
) -> ExecutiveScoringReportOut:
    """Genera el reporte ejecutivo completo basado en el ranking vigente."""
    ranking = get_ranking_in_force(db, club_id)
    if ranking is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NO_BASELINE", "message": NO_BASELINE_MESSAGE},
        )

    if ranking.population_size == 0:
        raise HTTPException(
            status_code=422,
            detail={"code": "EMPTY_RANKING", "message": EMPTY_RANKING_MESSAGE},
        )

    entries = db.scalars(
        select(RankingEntry)
        .where(RankingEntry.ranking_id == ranking.id)
        .order_by(RankingEntry.position)
    ).all()

    if not entries:
        raise HTTPException(
            status_code=422,
            detail={"code": "EMPTY_RANKING", "message": EMPTY_RANKING_MESSAGE},
        )

    club = db.scalar(select(Club).where(Club.id == club_id))
    club_name = club.nombre if club else "Club"

    rules_ver = db.scalar(
        select(RulesVersion).where(RulesVersion.id == ranking.rules_version_id)
    )
    if rules_ver is None:
        formula_id = "scoring-model"
        ver_number = 1
        param_dict: dict[str, str] = {}
    else:
        formula_id = rules_ver.formula_id
        ver_number = rules_ver.number
        param_dict = {k: str(v) for k, v in rules_ver.values.items()}

    socios = extract_executive_socios(entries)
    summary_out = compute_executive_summary(socios)
    histogram_out = compute_executive_histogram(socios)
    pillars_out = compute_pillars_average(socios)
    demographics_out = compute_executive_demographics(socios)

    now = datetime.now(UTC)

    metadata = ExecutiveReportMetadata(
        generated_at=now,
        generated_by=admin_email,
        club_id=club_id,
        club_name=club_name,
        ranking_id=ranking.id,
        ranking_calculated_at=ranking.completed_at or ranking.calculated_at,
        rules_version=RulesVersionParametersOut(
            formula_id=formula_id,
            version=ver_number,
            parameters=param_dict,
        ),
    )

    return ExecutiveScoringReportOut(
        metadata=metadata,
        summary=summary_out,
        histogram=histogram_out,
        pillars_average=pillars_out,
        demographic_equity=demographics_out,
    )


def export_executive_scoring_report_csv(
    db: Session, club_id: uuid.UUID, admin_email: str
) -> tuple[str, bytes]:
    """Genera y exporta el archivo CSV con los datos del reporte ejecutivo."""
    report = get_executive_scoring_report(db, club_id, admin_email)
    name = executive_report_filename(report.metadata.generated_at)
    content = executive_report_csv_bytes(report)
    return name, content

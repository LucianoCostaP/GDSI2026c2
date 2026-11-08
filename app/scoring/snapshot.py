"""Instantánea de entradas de un socio y su paso al motor (modelo de scoring, regla 4; FR-002).

Une los insumos de asistencia, participación institucional y pertenencia en los `ScoringInputs`
del motor. `scoring_inputs_from_snapshot` hace el camino inverso desde lo que quedó guardado en
la entrada del ranking: con esa instantánea y las mismas reglas, el motor da el mismo puntaje
(HU-18 y HU-29 recalculan sin releer el padrón ni las asistencias).

La instantánea también guarda todo lo que usa el desempate (regla 5): las fechas de inicio de
la antigüedad y de nacimiento (grupo `membership`) y el documento (grupo `tiebreak`). Así HU-18,
HU-29 y HU-30 reordenan con `ranking_candidate_from_snapshot` sin volver a leer `socios`.
"""

import uuid
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from .attendance_inputs import AttendanceInputs
from .engine import ScoringInputs
from .institutional_inputs import InstitutionalInputs
from .membership_inputs import MembershipInputs
from .ranking_order import RankingCandidate


def build_scoring_inputs(
    attendance: AttendanceInputs,
    institutional: InstitutionalInputs,
    membership: MembershipInputs,
) -> ScoringInputs:
    """Insumos del motor a partir de los tres grupos de datos del socio."""
    return ScoringInputs(
        matches_by_class=attendance.matches_by_class,
        attended_by_class=attendance.attended_by_class,
        distance_km=attendance.distance_km,
        institutional_points=Decimal(institutional.points),
        seniority_years=Decimal(membership.seniority_years),
        age_years=Decimal(membership.age_years),
        days_since_alta=membership.days_since_alta,
        days_since_previous_baja=membership.days_between_previous_baja_and_alta,
    )


def build_snapshot(
    attendance: AttendanceInputs,
    institutional: InstitutionalInputs,
    membership: MembershipInputs,
    *,
    dni: str,
) -> dict[str, Any]:
    """Instantánea serializable (JSON) que guarda cada entrada del ranking (regla 4)."""
    return {
        "attendance": attendance.as_dict(),
        "institutional": institutional.as_dict(),
        "membership": membership.as_dict(),
        "tiebreak": {"dni": dni},
    }


def ranking_candidate_from_snapshot(
    socio_id: uuid.UUID, total: Decimal, snapshot: Mapping[str, Any]
) -> RankingCandidate:
    """Candidato del ranking con un total dado y los desempates de la instantánea."""
    membership = snapshot["membership"]
    return RankingCandidate(
        socio_id=socio_id,
        total=total,
        seniority_start=date.fromisoformat(membership["seniority_start"]),
        birth_date=date.fromisoformat(membership["birth_date"]),
        dni=snapshot["tiebreak"]["dni"],
    )


def scoring_inputs_from_snapshot(snapshot: Mapping[str, Any]) -> ScoringInputs:
    """Reconstruye los insumos del motor desde la instantánea guardada en una entrada."""
    attendance = snapshot["attendance"]
    membership = snapshot["membership"]
    return ScoringInputs(
        matches_by_class=dict(attendance["matches_by_class"]),
        attended_by_class=dict(attendance["attended_by_class"]),
        distance_km=Decimal(attendance["distance_km"]),
        institutional_points=Decimal(snapshot["institutional"]["points"]),
        seniority_years=Decimal(membership["seniority_years"]),
        age_years=Decimal(membership["age_years"]),
        days_since_alta=membership["days_since_alta"],
        days_since_previous_baja=membership["days_between_previous_baja_and_alta"],
    )

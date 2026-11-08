"""Simulación del impacto de un cambio de reglas (HU-29).

La base de comparación es el último ranking completado del club, tal como quedó guardado, con
su propia versión de reglas (decisión 44). Nada de este módulo modifica datos reales ni escribe
en la auditoría (decisión 48).

Escenario 1: al abrir el simulador se muestran todos los parámetros de la fórmula, precargados
con los valores de la versión de reglas **del ranking** (no la vigente), con sus límites, los
valores derivados como solo lectura y la línea que dice contra qué ranking se compara.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import status
from sqlalchemy.orm import Session

from ..core.date_utils import a_hora_buenos_aires
from ..models import Ranking, RulesVersion
from ..schemas.rules_simulation import (
    BaselineRankingOut,
    DerivedValueOut,
    RulesSimulationFormOut,
)
from ..scoring.catalog import FormulaDescriptor, get_descriptor
from ..scoring.derived import derived_values
from ..scoring.formatting import decimal_to_str
from .formula_service import descriptor_out, error
from .ranking_service import get_ranking_in_force

NO_BASELINE_MESSAGE = (
    "Todavía no hay un ranking calculado, así que no hay con qué comparar. "
    "Calculá el ranking para poder simular."
)


def baseline_text(completed_at: datetime, rules_version: int) -> str:
    """Línea de la base (texto del spec), con la hora de Buenos Aires."""
    moment = a_hora_buenos_aires(completed_at).strftime("%d/%m/%Y %H:%M")
    return f"Comparado con el ranking calculado el {moment} (reglas versión {rules_version})."


def _baseline(db: Session, club_id: uuid.UUID) -> tuple[Ranking, RulesVersion]:
    """El último ranking completado del club y su versión de reglas, o `409 NO_BASELINE`."""
    ranking = get_ranking_in_force(db, club_id)
    if ranking is None:
        raise error(status.HTTP_409_CONFLICT, "NO_BASELINE", NO_BASELINE_MESSAGE)
    return ranking, db.get_one(RulesVersion, ranking.rules_version_id)


def _descriptor_of(rules: RulesVersion) -> FormulaDescriptor:
    descriptor = get_descriptor(rules.formula_id, rules.formula_version)
    # Una versión de reglas solo se publica con una fórmula del catálogo (HU-27).
    if descriptor is None:
        raise RuntimeError(
            f"La fórmula {rules.formula_id} v{rules.formula_version} de las reglas "
            f"{rules.id} no está en el catálogo."
        )
    return descriptor


def simulator_form(db: Session, club_id: uuid.UUID) -> RulesSimulationFormOut:
    """`GET /admin/rules-simulation`: base, formulario precargado y derivados (escenario 1)."""
    ranking, rules = _baseline(db, club_id)
    # Una corrida completada siempre tiene `completed_at` (`Ranking.mark_completed`).
    assert ranking.completed_at is not None
    descriptor = _descriptor_of(rules)
    # En el orden de los parámetros de la fórmula: JSONB no conserva el orden de las claves.
    values = {p.key: Decimal(rules.values[p.key]) for p in descriptor.parameters}
    derived = derived_values(descriptor, values)

    return RulesSimulationFormOut(
        ranking=BaselineRankingOut(
            id=ranking.id,
            completed_at=ranking.completed_at,
            calculation_date=ranking.calculation_date,
            rules_version=rules.number,
            population_size=ranking.population_size,
        ),
        baseline_text=baseline_text(ranking.completed_at, rules.number),
        formula=descriptor_out(descriptor),
        values={key: decimal_to_str(value) for key, value in values.items()},
        derived_values=[
            DerivedValueOut(
                symbol=d.symbol,
                name=d.name,
                expression=d.expression,
                value=(
                    decimal_to_str(derived[d.symbol]) if d.symbol in derived else None
                ),
            )
            for d in descriptor.derived_values
        ],
    )

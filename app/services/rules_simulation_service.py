"""Simulación del impacto de un cambio de reglas (HU-29).

La base de comparación es el último ranking completado del club, tal como quedó guardado, con
su propia versión de reglas (decisión 44). Nada de este módulo modifica datos reales ni escribe
en la auditoría (decisión 48).

Escenario 1: al abrir el simulador se muestran todos los parámetros de la fórmula, precargados
con los valores de la versión de reglas **del ranking** (no la vigente), con sus límites, los
valores derivados como solo lectura y la línea que dice contra qué ranking se compara.

Escenario 2: si las reglas vigentes no son las del ranking (por ejemplo, justo después de un
ajuste de HU-28), se avisa con las dos versiones y se mandan los valores vigentes para que el
front los cargue en el formulario. Cargarlos no simula ni cambia nada.

Escenario 4: si el último ranking completado no tiene socios, simular se rechaza con
`EMPTY_RANKING` antes de validar o calcular nada. Abrir el simulador no es error: el front ve
`population_size = 0` y no ofrece simular.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..core.date_utils import a_hora_buenos_aires
from ..models import Ranking, RulesVersion
from ..schemas.rules_simulation import (
    BaselineRankingOut,
    DerivedValueOut,
    RulesInForceOut,
    RulesSimulationFormOut,
    RulesSimulationResultOut,
)
from ..scoring.catalog import FormulaDescriptor, get_descriptor
from ..scoring.derived import derived_values
from ..scoring.formatting import decimal_to_str
from .formula_service import descriptor_out, error, get_in_force
from .ranking_service import get_ranking_in_force

NO_BASELINE_MESSAGE = (
    "Todavía no hay un ranking calculado, así que no hay con qué comparar. "
    "Calculá el ranking para poder simular."
)
EMPTY_RANKING_MESSAGE = "El último ranking no tiene socios: no hay nada para simular."


def rules_in_force_notice(in_force_version: int, ranking_version: int) -> str:
    """Aviso de que las reglas vigentes no son las del ranking (texto del spec)."""
    return (
        f"Las reglas vigentes (versión {in_force_version}) son distintas de las del ranking "
        f"(versión {ranking_version}). Podés cargarlas acá para ver cómo cambiaría el "
        "ranking en el próximo cálculo."
    )


def baseline_text(completed_at: datetime, rules_version: int) -> str:
    """Línea de la base (texto del spec), con la hora de Buenos Aires."""
    moment = a_hora_buenos_aires(completed_at).strftime("%d/%m/%Y %H:%M")
    return f"Comparado con el ranking calculado el {moment} (reglas versión {rules_version})."


def _rejection(code: str, message: str) -> HTTPException:
    """`409` con el formato de HU-27 y `Cache-Control: no-store`, como toda respuesta."""
    exc = error(status.HTTP_409_CONFLICT, code, message)
    exc.headers = {"Cache-Control": "no-store"}
    return exc


def _baseline(db: Session, club_id: uuid.UUID) -> tuple[Ranking, RulesVersion]:
    """El último ranking completado del club y su versión de reglas, o `409 NO_BASELINE`."""
    ranking = get_ranking_in_force(db, club_id)
    if ranking is None:
        raise _rejection("NO_BASELINE", NO_BASELINE_MESSAGE)
    return ranking, db.get_one(RulesVersion, ranking.rules_version_id)


def _baseline_out(ranking: Ranking, rules: RulesVersion) -> BaselineRankingOut:
    # Una corrida completada siempre tiene `completed_at` (`Ranking.mark_completed`).
    assert ranking.completed_at is not None
    return BaselineRankingOut(
        id=ranking.id,
        completed_at=ranking.completed_at,
        calculation_date=ranking.calculation_date,
        rules_version=rules.number,
        population_size=ranking.population_size,
    )


def _descriptor_of(rules: RulesVersion) -> FormulaDescriptor:
    descriptor = get_descriptor(rules.formula_id, rules.formula_version)
    # Una versión de reglas solo se publica con una fórmula del catálogo (HU-27).
    if descriptor is None:
        raise RuntimeError(
            f"La fórmula {rules.formula_id} v{rules.formula_version} de las reglas "
            f"{rules.id} no está en el catálogo."
        )
    return descriptor


def _values_of(rules: RulesVersion) -> dict[str, Decimal]:
    """Valores de una versión de reglas, en el orden de los parámetros de su fórmula.

    JSONB no conserva el orden de las claves; el formulario sí lo necesita.
    """
    descriptor = _descriptor_of(rules)
    return {p.key: Decimal(rules.values[p.key]) for p in descriptor.parameters}


def _as_text(values: dict[str, Decimal]) -> dict[str, str]:
    return {key: decimal_to_str(value) for key, value in values.items()}


def _rules_in_force(
    db: Session, club_id: uuid.UUID, ranking_rules: RulesVersion
) -> RulesInForceOut:
    """Las reglas vigentes si no son las del ranking (escenario 2).

    Cada ajuste (HU-28) o publicación (HU-27) crea una versión nueva y nunca repite los
    valores de la anterior, así que basta con comparar la versión.
    """
    in_force = get_in_force(db, club_id)
    if in_force is None or in_force.id == ranking_rules.id:
        return RulesInForceOut(differs=False)
    return RulesInForceOut(
        differs=True,
        version=in_force.number,
        values=_as_text(_values_of(in_force)),
        notice=rules_in_force_notice(in_force.number, ranking_rules.number),
    )


def simulator_form(db: Session, club_id: uuid.UUID) -> RulesSimulationFormOut:
    """`GET /admin/rules-simulation`: base, formulario precargado y derivados (escenario 1),
    y las reglas vigentes cuando no son las del ranking (escenario 2)."""
    ranking, rules = _baseline(db, club_id)
    baseline = _baseline_out(ranking, rules)
    descriptor = _descriptor_of(rules)
    values = _values_of(rules)
    derived = derived_values(descriptor, values)

    return RulesSimulationFormOut(
        ranking=baseline,
        baseline_text=baseline_text(baseline.completed_at, rules.number),
        formula=descriptor_out(descriptor),
        values=_as_text(values),
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
        rules_in_force=_rules_in_force(db, club_id, rules),
    )


def simulate(
    db: Session, club_id: uuid.UUID, raw_values: dict[str, Any]
) -> RulesSimulationResultOut:
    """`POST /admin/rules-simulation`: el ranking se fija al empezar (escenario 10).

    Orden de los rechazos: `NO_BASELINE` (escenario 3), `EMPTY_RANKING` (escenario 4) y
    después la validación de los valores (escenario 6).
    """
    ranking, rules = _baseline(db, club_id)
    if ranking.population_size == 0:
        raise _rejection("EMPTY_RANKING", EMPTY_RANKING_MESSAGE)
    baseline = _baseline_out(ranking, rules)
    return RulesSimulationResultOut(
        ranking=baseline,
        baseline_text=baseline_text(baseline.completed_at, rules.number),
    )

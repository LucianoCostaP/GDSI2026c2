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

Escenario 6: los valores hipotéticos se validan contra la fórmula de la versión de reglas del
ranking, con la misma validación, códigos y textos de HU-27 (`validate_values`); todas las
violaciones vuelven juntas en un `422 INVALID_VALUES` y no se calcula nada.

Escenario 7: el bloqueo de la fórmula (HU-27) y el corte de temporada (HU-28) gobiernan el
**guardado** de reglas oficiales, no la vista previa: simular no los consulta.

Escenario 8: cada entrada del ranking se recalcula desde su instantánea con el motor de HU-25
y se reordena con su desempate (`scoring.rules_simulation`). Solo se leen las entradas del
ranking: ni el padrón, ni las asistencias, ni las actividades.

Escenario 9: con los valores del ranking, todo da igual que lo guardado y el resultado lo dice
con `NO_CHANGES`.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.date_utils import a_hora_buenos_aires
from ..models import Ranking, RankingEntry, RulesVersion
from ..schemas.rules_simulation import (
    BaselineRankingOut,
    ChangedParameterOut,
    DerivedValueOut,
    MessageOut,
    MovementOut,
    RulesInForceOut,
    RulesSimulationFormOut,
    RulesSimulationResultOut,
)
from ..scoring.catalog import FormulaDescriptor, get_descriptor
from ..scoring.components import COMPONENT_KEYS
from ..scoring.derived import derived_values
from ..scoring.engine import ScoringParameters
from ..scoring.formatting import decimal_to_str
from ..scoring.rules_simulation import (
    StoredEntry,
    changed_keys,
    factor_of,
    factors_changed,
    movement,
    simulate_entries,
)
from ..scoring.validation import validate_values
from .formula_service import descriptor_out, error, get_in_force, violations_out
from .ranking_service import get_ranking_in_force

NO_BASELINE_MESSAGE = (
    "Todavía no hay un ranking calculado, así que no hay con qué comparar. "
    "Calculá el ranking para poder simular."
)
EMPTY_RANKING_MESSAGE = "El último ranking no tiene socios: no hay nada para simular."
INVALID_VALUES_MESSAGE = (
    "Hay valores que no se pueden simular. Corregilos y volvé a intentar."
)
NO_CHANGES_MESSAGE = (
    "Los valores son iguales a los del ranking: no hay diferencias para mostrar."
)


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


def _rejection(
    code: str, message: str, status_code: int = status.HTTP_409_CONFLICT, **extra: Any
) -> HTTPException:
    """Error con el formato de HU-27 y `Cache-Control: no-store`, como toda respuesta."""
    exc = error(status_code, code, message, **extra)
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
    # Límites y regla de la suma: los de la fórmula de las reglas del ranking (escenario 7).
    validation = validate_values(_descriptor_of(rules), raw_values)
    if not validation.valid:
        raise _rejection(
            "INVALID_VALUES",
            INVALID_VALUES_MESSAGE,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            violations=violations_out(validation.violations),
        )
    hypothetical = validation.values
    before_values = _values_of(rules)
    changed = changed_keys(before_values, hypothetical)

    before = stored_entries(db, ranking.id)
    after = simulate_entries(before, ScoringParameters.from_values(hypothetical))
    moved = movement(before, after)

    descriptor = _descriptor_of(rules)
    parameters = {p.key: p for p in descriptor.parameters}
    baseline = _baseline_out(ranking, rules)
    return RulesSimulationResultOut(
        ranking=baseline,
        baseline_text=baseline_text(baseline.completed_at, rules.number),
        status="changed" if changed else "no_changes",
        message=None
        if changed
        else MessageOut(code="NO_CHANGES", text=NO_CHANGES_MESSAGE),
        changed_parameters=[
            ChangedParameterOut(
                key=key,
                symbol=parameters[key].symbol,
                name=parameters[key].name,
                factor=factor_of(key),
                before=decimal_to_str(before_values[key]),
                after=decimal_to_str(hypothetical[key]),
            )
            for key in changed
        ],
        factors_changed=factors_changed(changed),
        movement=MovementOut(up=moved.up, down=moved.down, unchanged=moved.unchanged),
    )


def stored_entries(db: Session, ranking_id: int) -> list[StoredEntry]:
    """Las entradas del ranking tal como se guardaron, en orden de posición.

    Es lo único que lee la simulación (escenario 8): componentes, total, posición y la
    instantánea de insumos de cada socio.
    """
    columns = [getattr(RankingEntry, key) for key in COMPONENT_KEYS]
    rows = db.execute(
        select(
            RankingEntry.socio_id,
            RankingEntry.position,
            RankingEntry.total,
            RankingEntry.inputs,
            *columns,
        )
        .where(RankingEntry.ranking_id == ranking_id)
        .order_by(RankingEntry.position)
    )
    return [
        StoredEntry(
            socio_id=row.socio_id,
            position=row.position,
            components={key: getattr(row, key) for key in COMPONENT_KEYS},
            total=row.total,
            snapshot=row.inputs,
        )
        for row in rows
    ]

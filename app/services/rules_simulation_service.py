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

Escenarios 11 y 12: el histograma de 20 bins y las estadísticas (media, mediana, desvío,
percentiles 10 y 90) de los totales del ranking y de la simulación (`scoring.distribution`).

Escenario 13: el movimiento suma el cambio absoluto medio de posición y las subidas y bajadas
relevantes (al menos el 1 % del ranking).

Escenario 14: socios en el tope, con ajuste por tope, empatados y el empate más grande, en las
dos situaciones.

Escenario 15: las alertas de saturación y de concentración, calculadas con los valores exactos.

Escenario 16: el promedio de cada componente y del total en las dos situaciones; las seis
diferencias suman exactamente la del total.

Escenario 17: los parámetros cambiados, con los dos valores y su factor (pesos de los pilares,
`αA`, `dsat` u otros parámetros).

Escenario 18: con dos o más factores cambiados, el resultado principal avisa que el desglose
está pendiente y el front lo pide aparte (`breakdown`, contrato §6): una simulación por cada
factor cambiado entre pesos, `αA` y `dsat`, con solo sus valores sobre los del ranking,
ordenadas por cuánto mueven el ranking.

Escenario 19: junto a los aislados, la fila "Resto: otros parámetros e interacciones" con el
cambio de la simulación completa menos la suma de los aislados, los otros parámetros cambiados
y la nota de que los efectos no se suman.

Escenario 20: con un solo factor cambiado no se corre ninguna simulación aislada y el resultado
dice `SINGLE_FACTOR`; sin cambios, vale el escenario 9.

Escenario 21: el resultado principal no espera al desglose (que es otro pedido). Si el desglose
falla o supera su tiempo máximo (9 s hasta 50.000 socios, 30 s hasta 500.000), responde
`BREAKDOWN_UNAVAILABLE` y el resultado principal sigue valiendo.

Escenario 22: cada simulación aislada pasa la misma validación, usa el mismo motor y el mismo
desempate; el atajo por pilares (`PillarSimulator`) da exactamente el cálculo completo.

Escenario 23: el resultado va lado a lado con la situación actual: "Ranking actual" con su
versión de reglas y su fecha, y "Simulación" con los parámetros cambiados y los valores
derivados de antes y después. (El análisis de equidad de HU-30 todavía no está.)

Escenario 24: cada simulación es independiente. Nada se guarda entre pedidos ni dentro del
proceso: cada uno lee el ranking, recalcula y responde.

Escenario 25: no hace falta ajustar reglas (HU-28) ni calcular un ranking (HU-25) para
simular, y no hay forma de aplicar los valores: para hacerlos oficiales el Admin los carga en
HU-28 desde `changed_parameters`.

Escenario 26: el CSV con las cifras de la pantalla se arma en el momento sobre el mismo
ranking (`export`, formato en `rules_simulation_export`) y no se guarda.
"""

import logging
import time
import uuid
from collections.abc import Callable, Sequence
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.date_utils import a_hora_buenos_aires
from ..models import Ranking, RankingEntry, RankingState, RulesVersion, utcnow
from ..schemas.rules_simulation import (
    BaselineRankingOut,
    BreakdownOut,
    BreakdownStatusOut,
    ChangedParameterOut,
    ComponentChangeOut,
    DerivedChangeOut,
    DerivedValueOut,
    FactorEffectOut,
    FlatnessAlertOut,
    HistogramBinOut,
    LabelsOut,
    MessageOut,
    MovementOut,
    RemainderOut,
    RulesInForceOut,
    RulesSimulationFormOut,
    RulesSimulationResultOut,
    SaturationAlertOut,
    SaturationCountsOut,
    SaturationOut,
    StatsOut,
    SummaryOut,
)
from ..scoring.catalog import FormulaDescriptor, get_descriptor
from ..scoring.components import COMPONENT_KEYS
from ..scoring.derived import derived_values
from ..scoring.distribution import (
    BINS,
    TOTAL,
    ComponentChange,
    FlatnessAlert,
    Saturation,
    SaturationAlert,
    Summary,
    component_changes,
    flatness_alert,
    fraction_to_decimal,
    histogram,
    saturation,
    saturation_alert,
    summary,
)
from ..scoring.engine import ScoringParameters
from ..scoring.formatting import decimal_fixed, decimal_to_str
from ..scoring.rules_simulation import (
    OTHER,
    BreakdownTimeout,
    Deadline,
    FactorEffect,
    Movement,
    PillarSimulator,
    SimulatedEntry,
    StoredEntry,
    breakdown_budget,
    changed_keys,
    factor_of,
    factors_changed,
    factors_to_isolate,
    isolated_values,
    mean_total_change,
    movement,
    rank_effects,
    remainder_change,
    simulate_entries,
)
from ..scoring.validation import validate_values
from . import rules_simulation_export
from .formula_service import descriptor_out, error, get_in_force, violations_out
from .ranking_service import COMPONENT_NAMES, get_ranking_in_force

logger = logging.getLogger(__name__)

NO_BASELINE_MESSAGE = (
    "Todavía no hay un ranking calculado, así que no hay con qué comparar. "
    "Calculá el ranking para poder simular."
)
EMPTY_RANKING_MESSAGE = "El último ranking no tiene socios: no hay nada para simular."
INVALID_VALUES_MESSAGE = (
    "Hay valores que no se pueden simular. Corregilos y volvé a intentar."
)
SATURATION_ALERT_MESSAGE = (
    "Con estos valores {a} socios llegarían al tope de 100 (hoy {b}). "
    "Entre ellos el orden lo definirían la antigüedad y la edad."
)
FLATNESS_ALERT_MESSAGE = (
    "Con estos valores los puntajes se concentran: la dispersión baja un {x} %."
)
TOTAL_LABEL = "total"
NO_CHANGES_MESSAGE = (
    "Los valores son iguales a los del ranking: no hay diferencias para mostrar."
)
BASELINE_NOT_FOUND_MESSAGE = (
    "El ranking de esta simulación ya no está disponible. Volvé a simular."
)
SINGLE_FACTOR_MESSAGE = (
    "Cambiaste un solo grupo de parámetros: su efecto es el del resultado total."
)
AFTER_LABEL = "Simulación"
BREAKDOWN_PENDING_MESSAGE = "Calculando el efecto de cada parámetro…"
WEIGHS_MOST_MESSAGE = "Es el que más mueve el ranking."
REMAINDER_LABEL = "Resto: otros parámetros e interacciones"
BREAKDOWN_UNAVAILABLE_MESSAGE = "No pudimos calcular el efecto de cada parámetro. El resultado general sigue siendo válido."
NON_ADDITIVE_NOTE = "Los efectos de cada grupo no se suman: al combinarlos interactúan."
# El spec no las fija (contrato §9, punto 6).
FACTOR_LABELS = {
    "pillar_weights": "Pesos de los pilares",
    "alpha_a": "Peso de la distancia (αA)",
    "d_sat": "Punto de inflexión de la distancia (dsat)",
}


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


def labels(completed_at: datetime, rules_version: int) -> LabelsOut:
    """Títulos de las columnas (escenario 23). La fecha es la de la línea de la base: la del
    cálculo del ranking en hora de Buenos Aires, así la pantalla no muestra dos fechas."""
    day = a_hora_buenos_aires(completed_at).strftime("%d/%m/%Y")
    return LabelsOut(
        before=f"Ranking actual (reglas versión {rules_version}, {day})",
        after=AFTER_LABEL,
    )


def _derived_text(derived: dict[str, Decimal], symbol: str) -> str | None:
    return decimal_to_str(derived[symbol]) if symbol in derived else None


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
                value=_derived_text(derived, d.symbol),
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
    return _result(db, ranking, rules, raw_values)


def _result(
    db: Session, ranking: Ranking, rules: RulesVersion, raw_values: dict[str, Any]
) -> RulesSimulationResultOut:
    """El resultado principal sobre un ranking dado: el último (`simulate`) o el de la
    pantalla (`export`)."""
    hypothetical = _hypothetical_values(ranking, rules, raw_values)
    before_values = _values_of(rules)
    changed = changed_keys(before_values, hypothetical)

    before = stored_entries(db, ranking.id)
    after = simulate_entries(before, ScoringParameters.from_values(hypothetical))
    moved = movement(before, after)
    totals_before = [entry.total for entry in before]
    totals_after = [entry.total for entry in after]
    saturated_before = saturation(totals_before, _cap_adjustments(before))
    saturated_after = saturation(totals_after, _cap_adjustments(after))

    descriptor = _descriptor_of(rules)
    parameters = {p.key: p for p in descriptor.parameters}
    derived_before = derived_values(descriptor, before_values)
    derived_after = derived_values(descriptor, hypothetical)
    baseline = _baseline_out(ranking, rules)
    return RulesSimulationResultOut(
        ranking=baseline,
        baseline_text=baseline_text(baseline.completed_at, rules.number),
        status="changed" if changed else "no_changes",
        message=None
        if changed
        else MessageOut(code="NO_CHANGES", text=NO_CHANGES_MESSAGE),
        labels=labels(baseline.completed_at, rules.number),
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
        derived_values=[
            DerivedChangeOut(
                symbol=d.symbol,
                before=_derived_text(derived_before, d.symbol),
                after=_derived_text(derived_after, d.symbol),
            )
            for d in descriptor.derived_values
        ],
        summary=_summary_out(summary(totals_before), summary(totals_after)),
        movement=_movement_out(moved),
        histogram=_histogram_out(histogram(totals_before), histogram(totals_after)),
        saturation=SaturationOut(
            before=_saturation_out(saturated_before),
            after=_saturation_out(saturated_after),
        ),
        alerts=_alerts_out(
            saturation_alert(
                saturated_before, saturated_after, moved.relevant_threshold
            ),
            flatness_alert(totals_before, totals_after),
        ),
        components=[
            _component_out(change)
            for change in component_changes(
                COMPONENT_KEYS,
                ([e.components for e in before], totals_before),
                ([e.components for e in after], totals_after),
            )
        ],
        breakdown=_breakdown_status(changed),
    )


def _hypothetical_values(
    ranking: Ranking, rules: RulesVersion, raw_values: dict[str, Any]
) -> dict[str, Decimal]:
    """`EMPTY_RANKING` (escenario 4) y después la validación de los valores (escenario 6)."""
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
    return validation.values


def _breakdown_status(changed: list[str]) -> BreakdownStatusOut:
    """Si el front tiene que pedir el efecto de cada factor (escenarios 18 y 20)."""
    if not changed:
        return BreakdownStatusOut(status="no_changes", code=None, message=None)
    if not factors_to_isolate(factors_changed(changed)):
        return BreakdownStatusOut(
            status="single_factor", code="SINGLE_FACTOR", message=SINGLE_FACTOR_MESSAGE
        )
    return BreakdownStatusOut(
        status="pending", code=None, message=BREAKDOWN_PENDING_MESSAGE
    )


def _ranking_of(db: Session, club_id: uuid.UUID, ranking_id: int) -> Ranking:
    """El ranking del resultado principal, si sigue siendo un ranking completado del club.

    Aunque mientras tanto se haya completado otro, se usa este (escenario 10).
    """
    ranking = db.scalar(
        select(Ranking).where(
            Ranking.id == ranking_id,
            Ranking.club_id == club_id,
            Ranking.status == RankingState.COMPLETED,
        )
    )
    if ranking is None:
        raise _rejection("BASELINE_NOT_FOUND", BASELINE_NOT_FOUND_MESSAGE)
    return ranking


def breakdown(
    db: Session,
    club_id: uuid.UUID,
    ranking_id: int,
    raw_values: dict[str, Any],
    clock: Callable[[], float] | None = None,
) -> BreakdownOut:
    """`POST /admin/rules-simulation/breakdown`: una simulación por cada factor aislado
    (escenario 18) y el resto (escenario 19).

    Cada una aplica solo los valores hipotéticos de su factor sobre los de las reglas del
    ranking, con el mismo recálculo, desempate y validación que el resultado principal. El
    resto es el cambio de la simulación completa menos la suma de los aislados, con los
    valores exactos. Con un solo factor o ninguno no se simula nada más (escenario 20).
    Rechazos: `BASELINE_NOT_FOUND`, `EMPTY_RANKING` y `INVALID_VALUES`, en ese orden. Si el
    cálculo falla o supera su tiempo máximo (SC-006, medido con `clock` desde que llega el
    pedido), responde `unavailable` con `BREAKDOWN_UNAVAILABLE` (escenario 21).
    """
    ranking = _ranking_of(db, club_id, ranking_id)
    rules = db.get_one(RulesVersion, ranking.rules_version_id)
    hypothetical = _hypothetical_values(ranking, rules, raw_values)
    before_values = _values_of(rules)
    changed = changed_keys(before_values, hypothetical)
    isolated = factors_to_isolate(factors_changed(changed))
    if not isolated:
        state = _breakdown_status(changed)
        return BreakdownOut(
            ranking_id=ranking.id,
            status="no_changes" if state.status == "no_changes" else "single_factor",
            code=state.code,
            message=state.message,
            factors=[],
            remainder=None,
            non_additive_note=None,
        )

    deadline = Deadline(
        breakdown_budget(ranking.population_size), clock or time.monotonic
    )
    before = stored_entries(db, ranking.id)
    try:
        full_change, effects = _isolated_effects(
            _descriptor_of(rules), before, before_values, hypothetical, deadline
        )
    except BreakdownTimeout:
        logger.warning(
            "El desglose del ranking %s superó su tiempo máximo.", ranking.id
        )
        return _breakdown_unavailable(ranking.id)
    except Exception:
        # Escenario 21: el resultado principal ya está en pantalla y sigue valiendo.
        logger.exception("Falló el desglose del ranking %s.", ranking.id)
        return _breakdown_unavailable(ranking.id)

    return BreakdownOut(
        ranking_id=ranking.id,
        status="available",
        code=None,
        message=None,
        factors=[
            _factor_effect_out(effect, weighs_most=index == 0)
            for index, effect in enumerate(rank_effects(effects))
        ],
        remainder=RemainderOut(
            label=REMAINDER_LABEL,
            mean_total_change=decimal_fixed(
                fraction_to_decimal(remainder_change(full_change, effects)), 2
            ),
            parameters=[k for k in changed if factor_of(k) == OTHER],
        ),
        non_additive_note=NON_ADDITIVE_NOTE,
    )


def export(
    db: Session,
    club_id: uuid.UUID,
    ranking_id: int,
    raw_values: dict[str, Any],
    now: datetime | None = None,
) -> tuple[str, bytes]:
    """`POST /admin/rules-simulation/export`: el CSV de la pantalla (escenario 26).

    Recalcula el resultado principal y el desglose sobre el ranking de la pantalla, en el
    momento, y no guarda nada. Devuelve el nombre del archivo (hora de Buenos Aires de `now`)
    y su contenido. Rechazos: los de `breakdown`, en el mismo orden.
    """
    ranking = _ranking_of(db, club_id, ranking_id)
    rules = db.get_one(RulesVersion, ranking.rules_version_id)
    result = _result(db, ranking, rules, raw_values)
    factors = breakdown(db, club_id, ranking_id, raw_values)
    in_force = get_in_force(db, club_id)
    rows = rules_simulation_export.csv_rows(
        result, factors, in_force.number if in_force else rules.number
    )
    return (
        rules_simulation_export.filename(now or utcnow()),
        rules_simulation_export.csv_bytes(rows),
    )


def _isolated_effects(
    descriptor: FormulaDescriptor,
    before: list[StoredEntry],
    before_values: dict[str, Decimal],
    hypothetical: dict[str, Decimal],
    deadline: Deadline,
) -> tuple[Fraction, list[FactorEffect]]:
    """El cambio del total medio de la simulación completa y el efecto de cada factor aislado.

    Todas reusan los pilares (`PillarSimulator`, escenario 22). Cada juego de valores aislado
    pasa la misma validación que los del Admin; uno inválido es una falla del desglose.
    """
    changed = changed_keys(before_values, hypothetical)
    simulator = PillarSimulator(before, deadline.check)
    full = simulator.run(ScoringParameters.from_values(hypothetical))
    effects = []
    for factor in factors_to_isolate(factors_changed(changed)):
        values = isolated_values(before_values, hypothetical, factor)
        if not validate_values(descriptor, values).valid:
            raise RuntimeError(f"Los valores aislados de {factor} no son válidos.")
        after = simulator.run(ScoringParameters.from_values(values))
        effects.append(
            FactorEffect(
                factor=factor,
                parameters=tuple(k for k in changed if factor_of(k) == factor),
                mean_total_change=mean_total_change(before, after),
                movement=movement(before, after),
            )
        )
    return mean_total_change(before, full), effects


def _breakdown_unavailable(ranking_id: int) -> BreakdownOut:
    return BreakdownOut(
        ranking_id=ranking_id,
        status="unavailable",
        code="BREAKDOWN_UNAVAILABLE",
        message=BREAKDOWN_UNAVAILABLE_MESSAGE,
        factors=[],
        remainder=None,
        non_additive_note=None,
    )


def _factor_effect_out(effect: FactorEffect, *, weighs_most: bool) -> FactorEffectOut:
    return FactorEffectOut(
        factor=effect.factor,
        label=FACTOR_LABELS[effect.factor],
        parameters=list(effect.parameters),
        mean_total_change=decimal_fixed(
            fraction_to_decimal(effect.mean_total_change), 2
        ),
        up=effect.movement.up,
        down=effect.movement.down,
        mean_abs_position_change=decimal_fixed(
            effect.movement.mean_abs_position_change, 1
        ),
        weighs_most=weighs_most,
        weighs_most_text=WEIGHS_MOST_MESSAGE if weighs_most else None,
    )


def _alerts_out(
    saturated: SaturationAlert | None, flat: FlatnessAlert | None
) -> list[SaturationAlertOut | FlatnessAlertOut]:
    alerts: list[SaturationAlertOut | FlatnessAlertOut] = []
    if saturated:
        alerts.append(
            SaturationAlertOut(
                text=SATURATION_ALERT_MESSAGE.format(
                    a=saturated.at_cap_after, b=saturated.at_cap_before
                ),
                at_cap_after=saturated.at_cap_after,
                at_cap_before=saturated.at_cap_before,
            )
        )
    if flat:
        drop = decimal_fixed(flat.drop_percent, 1)
        alerts.append(
            FlatnessAlertOut(
                text=FLATNESS_ALERT_MESSAGE.format(x=drop.replace(".", ",")),
                drop_percent=drop,
            )
        )
    return alerts


def _component_out(change: ComponentChange) -> ComponentChangeOut:
    return ComponentChangeOut(
        key=change.key,
        label=TOTAL_LABEL if change.key == TOTAL else COMPONENT_NAMES[change.key],
        before=decimal_fixed(fraction_to_decimal(change.before), 2),
        after=decimal_fixed(fraction_to_decimal(change.after), 2),
        difference=decimal_fixed(fraction_to_decimal(change.difference), 2),
    )


def _movement_out(moved: Movement) -> MovementOut:
    return MovementOut(
        up=moved.up,
        down=moved.down,
        unchanged=moved.unchanged,
        mean_abs_position_change=decimal_fixed(moved.mean_abs_position_change, 1),
        relevant_threshold=moved.relevant_threshold,
        relevant_up=moved.relevant_up,
        relevant_down=moved.relevant_down,
    )


def _cap_adjustments(entries: Sequence[StoredEntry | SimulatedEntry]) -> list[Decimal]:
    return [entry.components["cap_adjustment"] for entry in entries]


def _saturation_out(counts: Saturation) -> SaturationCountsOut:
    return SaturationCountsOut(
        at_cap=counts.at_cap,
        needs_cap_adjustment=counts.needs_cap_adjustment,
        tied=counts.tied,
        largest_tie=counts.largest_tie,
    )


def _stats_out(stats: Summary) -> StatsOut:
    return StatsOut(
        mean=decimal_fixed(stats.mean, 2),
        median=decimal_fixed(stats.median, 2),
        std_dev=decimal_fixed(stats.std_dev, 2),
        p10=decimal_fixed(stats.p10, 2),
        p90=decimal_fixed(stats.p90, 2),
    )


def _summary_out(before: Summary, after: Summary) -> SummaryOut:
    """Escenario 12: la diferencia sale de los valores exactos, redondeada al final."""
    return SummaryOut(
        before=_stats_out(before),
        after=_stats_out(after),
        difference=_stats_out(after.minus(before)),
    )


def _histogram_out(before: list[int], after: list[int]) -> list[HistogramBinOut]:
    return [
        HistogramBinOut(
            label=bin_.label,
            lower=str(bin_.lower),
            upper=str(bin_.upper),
            before=count_before,
            after=count_after,
        )
        for bin_, count_before, count_after in zip(BINS, before, after, strict=True)
    ]


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

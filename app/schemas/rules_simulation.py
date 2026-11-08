"""Respuestas de la simulación de cambio de reglas (HU-29).

Contrato con el front: `docs/contrato-api-simulacion-reglas.md`. Los decimales viajan como
texto, nunca como número de coma flotante.
"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel


class BaselineRankingOut(BaseModel):
    """El ranking contra el que se compara: el último completado del club (escenario 1)."""

    id: int
    completed_at: datetime
    calculation_date: date
    # Número de la versión de reglas que usó ese ranking (no el de las vigentes).
    rules_version: int
    population_size: int


class DerivedValueOut(BaseModel):
    """Valor derivado de la fórmula, de solo lectura (por ejemplo `b`)."""

    symbol: str
    name: str
    expression: str
    # Calculado con los valores precargados; `null` si la fórmula no tiene cálculo conocido.
    value: str | None


class RulesInForceOut(BaseModel):
    """Las reglas vigentes, cuando no son las del ranking (escenario 2).

    El front ofrece "Cargar reglas vigentes", que solo copia `values` al formulario: no
    simula ni cambia nada. Si son las mismas reglas, `differs` es `false` y el resto `null`.
    """

    differs: bool
    version: int | None = None
    values: dict[str, str] | None = None
    notice: str | None = None


class RulesSimulationFormOut(BaseModel):
    """`GET /admin/rules-simulation`: lo necesario para abrir el simulador (contrato §3)."""

    ranking: BaselineRankingOut
    baseline_text: str
    # Descriptor de la fórmula de la versión de reglas del ranking, con la misma forma que
    # `GET /admin/formulas/{id}/{version}` (parámetros, límites, restricción de suma).
    formula: dict[str, Any]
    # Valores de la versión de reglas del ranking, por clave de parámetro.
    values: dict[str, str]
    derived_values: list[DerivedValueOut]
    rules_in_force: RulesInForceOut


class SimulationRequest(BaseModel):
    """Cuerpo de los `POST` (contrato §4): los valores hipotéticos, por clave de parámetro.

    Llegan sin tipar (`Any`) para que la validación de HU-27 diga qué valor no es un número.
    Un `club_id` que venga en el cuerpo se ignora (escenario 5).
    """

    values: dict[str, Any]


class MessageOut(BaseModel):
    """Mensaje del resultado con su código (por ejemplo `NO_CHANGES`)."""

    code: str
    text: str


class ChangedParameterOut(BaseModel):
    """Un parámetro cuyo valor hipotético difiere del de las reglas del ranking (esc. 17)."""

    key: str
    symbol: str
    name: str
    # `pillar_weights` | `alpha_a` | `d_sat` | `other`.
    factor: str
    before: str
    after: str


class MovementOut(BaseModel):
    """Socios que suben, bajan o quedan igual frente al ranking (escenario 13).

    `up + down + unchanged` es la población del ranking. `relevant_up` y `relevant_down`
    cuentan a los que cambian al menos `relevant_threshold` posiciones (el 1 % del ranking).
    """

    up: int
    down: int
    unchanged: int
    # Un decimal, mitad hacia arriba.
    mean_abs_position_change: str
    relevant_threshold: int
    relevant_up: int
    relevant_down: int


class SaturationCountsOut(BaseModel):
    """Tope, ajuste por tope y empates de una situación (escenario 14)."""

    at_cap: int
    needs_cap_adjustment: int
    tied: int
    largest_tie: int


class SaturationOut(BaseModel):
    before: SaturationCountsOut
    after: SaturationCountsOut


class StatsOut(BaseModel):
    """Estadísticas de los totales, con 2 decimales para mostrar (escenario 12)."""

    mean: str
    median: str
    std_dev: str
    p10: str
    p90: str


class SummaryOut(BaseModel):
    """Las estadísticas del ranking, las de la simulación y su diferencia (simulación − ranking).

    La diferencia se calcula con los valores exactos y se redondea al final.
    """

    before: StatsOut
    after: StatsOut
    difference: StatsOut


class HistogramBinOut(BaseModel):
    """Un bin de 5 puntos con los socios del ranking y de la simulación (escenario 11)."""

    label: str
    lower: str
    upper: str
    before: int
    after: int


class SaturationAlertOut(BaseModel):
    """Escenario 15: con los valores hipotéticos muchos más socios llegan a 100."""

    code: Literal["SATURATION_ALERT"] = "SATURATION_ALERT"
    text: str
    at_cap_after: int
    at_cap_before: int


class FlatnessAlertOut(BaseModel):
    """Escenario 15: el desvío baja al 80 % o menos del del ranking."""

    code: Literal["FLATNESS_ALERT"] = "FLATNESS_ALERT"
    text: str
    # Un decimal, mitad hacia arriba; en `text` va con coma.
    drop_percent: str


class ComponentChangeOut(BaseModel):
    """Promedio de un componente (o del total) en el ranking y en la simulación (escenario 16).

    La diferencia se calcula con los valores exactos y se redondea al final.
    """

    key: str
    label: str
    before: str
    after: str
    difference: str


class BreakdownStatusOut(BaseModel):
    """Qué pasa con el efecto de cada factor (escenarios 18 y 20).

    `pending`: cambiaron dos o más factores y el front pide `POST /breakdown`;
    `single_factor`: cambió uno solo (código `SINGLE_FACTOR`); `no_changes`: no cambió nada.
    """

    status: Literal["pending", "single_factor", "no_changes"]
    code: str | None
    message: str | None


class RulesSimulationResultOut(BaseModel):
    """`POST /admin/rules-simulation`: resultado principal (contrato §5).

    Por ahora trae la base, si hubo cambios, los parámetros cambiados, las estadísticas, el
    movimiento de posiciones, el histograma, la saturación, las alertas, el cambio por
    componente y si hay que pedir el desglose por factor; falta la equidad (HU-30).
    """

    ranking: BaselineRankingOut
    baseline_text: str
    # `changed` | `no_changes` (ningún valor difiere del ranking, escenario 9).
    status: str
    message: MessageOut | None
    changed_parameters: list[ChangedParameterOut]
    factors_changed: list[str]
    summary: SummaryOut
    movement: MovementOut
    # Siempre los 20 bins, del más bajo al más alto.
    histogram: list[HistogramBinOut]
    saturation: SaturationOut
    # Ninguna, una o las dos (saturación primero); ninguna bloquea nada.
    alerts: list[SaturationAlertOut | FlatnessAlertOut]
    # Los seis componentes en el orden de HU-16 y el total al final.
    components: list[ComponentChangeOut]
    breakdown: BreakdownStatusOut


class BreakdownRequest(SimulationRequest):
    """Cuerpo de `POST /breakdown` (contrato §6): los mismos valores del resultado principal y
    el ranking de ese resultado, para no mezclar rankings (escenario 10)."""

    ranking_id: int


class FactorEffectOut(BaseModel):
    """Lo que mueve un factor solo, sobre los valores del ranking (escenario 18)."""

    factor: str
    label: str
    # Los parámetros cambiados de ese factor.
    parameters: list[str]
    # Cambio del total medio (simulación − ranking), 2 decimales.
    mean_total_change: str
    up: int
    down: int
    # Un decimal, mitad hacia arriba.
    mean_abs_position_change: str
    # Solo el primero: el que más mueve el ranking.
    weighs_most: bool
    weighs_most_text: str | None


class BreakdownOut(BaseModel):
    """`POST /admin/rules-simulation/breakdown`: efecto de cada factor (contrato §6).

    `available` con una entrada por factor aislado, ordenadas de la que más mueve a la que
    menos; `single_factor` o `no_changes` sin ninguna.
    """

    ranking_id: int
    status: Literal["available", "single_factor", "no_changes"]
    code: str | None
    message: str | None
    factors: list[FactorEffectOut]

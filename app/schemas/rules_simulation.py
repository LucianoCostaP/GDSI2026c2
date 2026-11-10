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


class LabelsOut(BaseModel):
    """Títulos de las dos columnas del resultado (escenario 23).

    `before`: "Ranking actual" con la versión de reglas y la fecha del ranking; `after`:
    "Simulación" (los parámetros cambiados viajan en `changed_parameters`).
    """

    before: str
    after: str


class DerivedChangeOut(BaseModel):
    """Un valor derivado de la fórmula con los valores del ranking y con los hipotéticos.

    `null` en los dos si la fórmula no tiene cálculo conocido para ese derivado.
    """

    symbol: str
    before: str | None
    after: str | None


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


# --- Esquemas de equidad (HU-30, contrato §5.3) -------------------------------------------


class MoverVariableOut(BaseModel):
    """Una variable del perfil con su valor en el grupo, en Todos y su diferencia."""

    value: str
    all: str
    difference: str


class MoverClassCOut(BaseModel):
    """Asistencia a partidos Clase C: se muestra solo para socios con al menos 1 partido."""

    value: str | None
    all: str | None
    difference: str | None
    count: int
    too_small: bool
    message: str | None


class MoverVariablesOut(BaseModel):
    """Las 5 variables del perfil de un grupo (escenario 5)."""

    distance_km: MoverVariableOut
    seniority_years: MoverVariableOut
    age_years: MoverVariableOut
    class_c_attendance: MoverClassCOut
    institutional_points: MoverVariableOut
    with_institutional: MoverVariableOut


class MoverGroupOut(BaseModel):
    """Un grupo del perfil: Suben, Bajan, Sin cambio relevante o Todos (escenario 4)."""

    group: Literal["up", "down", "no_change", "all"]
    label: str
    count: int
    share: str
    too_small: bool
    message: str | None
    variables: MoverVariablesOut | None


class MoverProfileOut(BaseModel):
    """Perfil de los socios que se mueven frente al ranking (escenario 4)."""

    relevant_threshold: int
    groups: list[MoverGroupOut]


class BandOut(BaseModel):
    """Una banda de un atributo, inicial o fusionada."""

    lower: str
    upper: str | None
    label: str


class SegmentOut(BaseModel):
    """Un segmento de un atributo con sus métricas y desvío (escenario 9)."""

    band: BandOut
    count: int
    avg_score_before: str
    avg_score_after: str
    avg_score_difference: str
    avg_position_before: str
    avg_position_after: str
    avg_position_change: str
    deviation: str
    mark: Literal["none", "marked", "strong"]
    direction: Literal["favored", "harmed"] | None
    largest_deviation: bool


class AttributeVerdictOut(BaseModel):
    """Veredicto particular de un atributo (escenario 14)."""

    code: Literal["EQUITY_OK", "EQUITY_ATTENTION", "EQUITY_BIAS"]
    text: str


class SegmentationOut(BaseModel):
    """Segmentación de los socios por un atributo (antigüedad, distancia o edad)."""

    attribute: Literal["seniority", "distance", "age"]
    label: str
    status: Literal["available", "not_available"]
    code: str | None = None
    message: str | None = None
    segments: list[SegmentOut]
    verdict: AttributeVerdictOut | None = None


class VerdictItemOut(BaseModel):
    """Un grupo marcado o fuerte dentro del veredicto general."""

    attribute: str
    band: str
    direction: Literal["favored", "harmed"]
    deviation: str
    mark: Literal["marked", "strong"]


class OverallVerdictOut(BaseModel):
    """Veredicto general de equidad (el más severo de los disponibles, escenario 14)."""

    code: Literal["EQUITY_OK", "EQUITY_ATTENTION", "EQUITY_BIAS"]
    text: str
    scope: str
    items: list[VerdictItemOut]


class EquityOut(BaseModel):
    """`equity`: análisis de impacto en perfiles y equidad por segmentos (HU-30)."""

    status: Literal["available", "unavailable"]
    code: str | None = None
    message: str | None = None
    profile: MoverProfileOut | None = None
    segmentations: list[SegmentationOut] | None = None
    verdict: OverallVerdictOut | None = None


class RulesSimulationResultOut(BaseModel):
    """`POST /admin/rules-simulation`: resultado principal (contrato §5).

    Incluye la base, parámetros cambiados, valores derivados, estadísticas, movimiento,
    histograma, saturación, alertas, cambio por componente, estado del desglose y análisis de
    equidad (HU-30).
    """

    ranking: BaselineRankingOut
    baseline_text: str
    # `changed` | `no_changes` (ningún valor difiere del ranking, escenario 9).
    status: str
    message: MessageOut | None
    labels: LabelsOut
    changed_parameters: list[ChangedParameterOut]
    factors_changed: list[str]
    derived_values: list[DerivedChangeOut]
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
    equity: EquityOut


class BreakdownRequest(SimulationRequest):
    """Cuerpo de `POST /breakdown` (contrato §6): los mismos valores del resultado principal y
    el ranking de ese resultado, para no mezclar rankings (escenario 10)."""

    ranking_id: int


class ExportRequest(BreakdownRequest):
    """Cuerpo de `POST /export` (contrato §7): el CSV es del mismo ranking que la pantalla."""


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


class RemainderOut(BaseModel):
    """Escenario 19: lo que no explican los factores aislados.

    `mean_total_change` = cambio de la simulación completa − suma de los aislados (2 decimales,
    calculado con los valores exactos). `parameters`: los otros parámetros cambiados; vacío si
    el resto es solo interacción.
    """

    label: str
    mean_total_change: str
    parameters: list[str]


class BreakdownOut(BaseModel):
    """`POST /admin/rules-simulation/breakdown`: efecto de cada factor (contrato §6).

    `available` con una entrada por factor aislado, ordenadas de la que más mueve a la que
    menos, el resto y la nota de no aditividad; `single_factor` o `no_changes` sin ninguna,
    con `remainder` y `non_additive_note` en `null` (escenario 20); `unavailable` con
    `BREAKDOWN_UNAVAILABLE` si falló o superó su tiempo máximo (escenario 21).
    """

    ranking_id: int
    status: Literal["available", "single_factor", "no_changes", "unavailable"]
    code: str | None
    message: str | None
    factors: list[FactorEffectOut]
    remainder: RemainderOut | None
    non_additive_note: str | None

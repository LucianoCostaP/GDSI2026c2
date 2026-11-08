"""Respuestas de la simulación de cambio de reglas (HU-29).

Contrato con el front: `docs/contrato-api-simulacion-reglas.md`. Los decimales viajan como
texto, nunca como número de coma flotante.
"""

from datetime import date, datetime
from typing import Any

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

    `up + down + unchanged` es la población del ranking.
    """

    up: int
    down: int
    unchanged: int


class RulesSimulationResultOut(BaseModel):
    """`POST /admin/rules-simulation`: resultado principal (contrato §5).

    Por ahora trae la base, si hubo cambios, los parámetros cambiados y el movimiento de
    posiciones; las demás secciones (distribución, saturación, componentes, equidad) llegan
    con los escenarios 11 a 16 y HU-30.
    """

    ranking: BaselineRankingOut
    baseline_text: str
    # `changed` | `no_changes` (ningún valor difiere del ranking, escenario 9).
    status: str
    message: MessageOut | None
    changed_parameters: list[ChangedParameterOut]
    factors_changed: list[str]
    movement: MovementOut

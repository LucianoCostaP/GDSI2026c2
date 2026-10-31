"""Motor de scoring del modelo base v1 (HU-25, Ciclo 0; spec `scoring-model.md`).

Código puro y determinístico: sin base de datos, sin reloj y sin tipos binarios de punto
flotante. Es la única implementación del cálculo (constitución, principio 1): la usan HU-25,
HU-18, HU-29 y HU-30. Recibe los insumos crudos de un socio y los parámetros de la versión de
reglas, y devuelve los seis componentes del puntaje con su total.

Aritmética: todo en `Decimal`, incluidas las curvas (`exp`). El cálculo corre en un contexto
decimal propio, así el resultado no depende de la configuración global del proceso. Cada
componente se redondea a 2 decimales (mitad hacia arriba) y el total es la suma de los
componentes ya redondeados (regla 1 del modelo).
"""

from collections.abc import Mapping
from dataclasses import dataclass, fields
from decimal import ROUND_HALF_UP, Context, Decimal, localcontext
from typing import Any

from .attendance_inputs import MATCH_CLASSES
from .catalog import SCORING_MODEL_V1
from .components import total_of
from .validation import parse_decimal

# Factor C(I) de cada clase de partido: constantes de la fórmula, no editables.
CLASS_FACTORS: Mapping[str, Decimal] = {
    "A": Decimal("1.0"),
    "B": Decimal("1.3"),
    "C": Decimal("1.8"),
}
# Pendiente de la curva de distancia: b = 4,356 / dsat.
GOMPERTZ_SLOPE = Decimal("4.356")

_CONTEXT = Context(prec=40)
_ZERO = Decimal("0.00")
_CENT = Decimal("0.01")
_FULL_SCORE = Decimal("100.00")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def round_component(value: Decimal) -> Decimal:
    """Redondeo a 2 decimales, mitad hacia arriba (regla 1)."""
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ScoringParameters:
    """Parámetros de una versión de reglas (modelo, sección 4). Los nombres son las claves."""

    w_a: Decimal
    w_p: Decimal
    w_t: Decimal
    alpha_a: Decimal
    d_sat: Decimal
    p_inst_max: Decimal
    alpha_t: Decimal
    t_ref: Decimal
    e_ref: Decimal
    gamma: Decimal
    b_max: Decimal
    t_max: Decimal
    t_carencia: Decimal

    def __post_init__(self) -> None:
        for name in ("d_sat", "t_ref", "e_ref", "t_max"):
            _require(getattr(self, name) > 0, f"El parámetro {name} tiene que ser > 0.")

    @classmethod
    def from_values(cls, values: Mapping[str, Any]) -> "ScoringParameters":
        """Arma los parámetros desde `RulesVersion.values` (decimales guardados como texto)."""
        expected = {f.name for f in fields(cls)}
        _require(
            set(values) == expected,
            f"Se esperaban los parámetros {sorted(expected)}, llegaron {sorted(values)}.",
        )
        parsed: dict[str, Decimal] = {}
        for key, raw in values.items():
            number = parse_decimal(raw)
            _require(
                number is not None, f"El parámetro {key} no es un número: {raw!r}."
            )
            assert number is not None
            parsed[key] = number
        return cls(**parsed)

    @classmethod
    def defaults(cls) -> "ScoringParameters":
        """Los valores por defecto del catálogo (scoring-model, versión 1)."""
        return cls.from_values(
            {p.key: str(p.default) for p in SCORING_MODEL_V1.parameters}
        )


@dataclass(frozen=True)
class ScoringInputs:
    """Insumos crudos de un socio (modelo, regla 4: instantánea de entradas)."""

    # Partidos del denominador y a los que fue, por clase (ver `attendance_inputs`).
    matches_by_class: Mapping[str, int]
    attended_by_class: Mapping[str, int]
    # `di`: distancia del socio al estadio.
    distance_km: Decimal
    # Σ(Vk·Ak) + Σ(Dm·tm) antes del tope: puntos de eventos institucionales y de actividades.
    institutional_points: Decimal
    # T y E: años de antigüedad ininterrumpida y edad, a la fecha de cálculo.
    seniority_years: Decimal
    age_years: Decimal
    # t: días desde el alta.
    days_since_alta: int
    # Días entre una baja previa y el alta actual; `None` si nunca tuvo una baja.
    days_since_previous_baja: int | None = None

    def __post_init__(self) -> None:
        classes = set(MATCH_CLASSES)
        _require(
            set(self.matches_by_class) == classes
            and set(self.attended_by_class) == classes,
            f"Los conteos tienen que traer exactamente las clases {MATCH_CLASSES}.",
        )
        for match_class in MATCH_CLASSES:
            matches = self.matches_by_class[match_class]
            attended = self.attended_by_class[match_class]
            _require(
                0 <= attended <= matches,
                f"Clase {match_class}: los asistidos ({attended}) tienen que estar entre "
                f"0 y los partidos ({matches}).",
            )
        _require(self.distance_km >= 0, "La distancia no puede ser negativa.")
        _require(
            self.institutional_points >= 0,
            "Los puntos institucionales no pueden ser negativos.",
        )
        _require(
            self.seniority_years >= 0 and self.age_years >= 0,
            "La antigüedad y la edad no pueden ser negativas.",
        )
        _require(
            self.days_since_alta >= 0, "Los días desde el alta no pueden ser negativos."
        )
        _require(
            self.days_since_previous_baja is None or self.days_since_previous_baja >= 0,
            "Los días desde la baja previa no pueden ser negativos.",
        )


@dataclass(frozen=True)
class ScoreResult:
    """Los seis componentes (ya redondeados) y su total."""

    components: dict[str, Decimal]
    total: Decimal


# --- Pilares (sin redondear) --------------------------------------------------------------


def frequency_score(
    matches_by_class: Mapping[str, int], attended_by_class: Mapping[str, int]
) -> Decimal:
    """P_frecuencia = 100 · Σ asistidos C(I) / Σ totales C(I); denominador 0 da 0."""
    total = sum(
        (CLASS_FACTORS[c] * matches_by_class[c] for c in MATCH_CLASSES), Decimal(0)
    )
    if total == 0:
        return Decimal(0)
    attended = sum(
        (CLASS_FACTORS[c] * attended_by_class[c] for c in MATCH_CLASSES), Decimal(0)
    )
    return 100 * attended / total


def distance_score(
    distance_km: Decimal, attended_matches: int, d_sat: Decimal
) -> Decimal:
    """P_distancia: curva de Gompertz con punto de inflexión en `d_sat`.

    La distancia es la misma en todos los partidos del socio, así que el promedio sobre los
    asistidos es el valor de la curva en `di`. Sin asistidos (N = 0) da 0.
    """
    if attended_matches == 0:
        return Decimal(0)
    slope = GOMPERTZ_SLOPE / d_sat
    inner = (-slope * (distance_km - d_sat)).exp()
    return 100 * (-inner).exp()


def institutional_score(points: Decimal, cap: Decimal) -> Decimal:
    """P_inst = min(Pinst_max, puntos)."""
    return min(cap, points)


def seniority_age_score(
    seniority_years: Decimal, age_years: Decimal, params: ScoringParameters
) -> Decimal:
    """P_antigüedad = 100 · min(1, [(αT·T + (1−αT)·E) / (αT·Tref + (1−αT)·Eref)]^γ)."""
    weight = params.alpha_t
    ratio = (weight * seniority_years + (1 - weight) * age_years) / (
        weight * params.t_ref + (1 - weight) * params.e_ref
    )
    return 100 * min(Decimal(1), ratio**params.gamma)


def new_member_bonus(
    days_since_alta: int,
    days_since_previous_baja: int | None,
    params: ScoringParameters,
) -> Decimal:
    """B_nuevo lineal: Bmax · max(0, 1 − t/Tmax); 0 con una baja previa dentro de la carencia."""
    if (
        days_since_previous_baja is not None
        and days_since_previous_baja < params.t_carencia
    ):
        return Decimal(0)
    remaining = 1 - Decimal(days_since_alta) / params.t_max
    return params.b_max * max(Decimal(0), remaining)


# --- Puntaje -------------------------------------------------------------------------------


def calculate_score(inputs: ScoringInputs, params: ScoringParameters) -> ScoreResult:
    """Puntaje de un socio: seis componentes redondeados y su total (reglas 1 a 3)."""
    with localcontext(_CONTEXT):
        attended_matches = sum(inputs.attended_by_class.values())
        frequency = frequency_score(inputs.matches_by_class, inputs.attended_by_class)
        distance = distance_score(inputs.distance_km, attended_matches, params.d_sat)
        institutional = institutional_score(
            inputs.institutional_points, params.p_inst_max
        )
        seniority_age = seniority_age_score(
            inputs.seniority_years, inputs.age_years, params
        )

        components = {
            "attendance_frequency": round_component(
                params.w_a * (1 - params.alpha_a) * frequency
            ),
            "attendance_distance": round_component(
                params.w_a * params.alpha_a * distance
            ),
            "institutional": round_component(params.w_p * institutional),
            "seniority_age": round_component(params.w_t * seniority_age),
            "new_member_bonus": round_component(
                new_member_bonus(
                    inputs.days_since_alta, inputs.days_since_previous_baja, params
                )
            ),
        }
        subtotal = sum(components.values(), _ZERO)
        # Regla 2: si la suma pasa de 100, el ajuste negativo deja el total en 100.
        components["cap_adjustment"] = (
            _FULL_SCORE - subtotal if subtotal > _FULL_SCORE else _ZERO
        )
        return ScoreResult(components=components, total=total_of(components))

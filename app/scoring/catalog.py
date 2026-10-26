"""Catálogo de fórmulas (scoring model, sección 7).

Cada entrada es un *descriptor* que viaja con el producto. El Admin elige una y la publica (HU-27);
no puede crear ni editar fórmulas. Agregar una entrada es un release del producto.
"""

import string
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Variable:
    key: str
    name: str
    description: str


@dataclass(frozen=True)
class Parameter:
    key: str
    symbol: str
    name: str
    unit: str
    default: Decimal
    minimum: Decimal
    maximum: Decimal
    description: str


@dataclass(frozen=True)
class Constant:
    symbol: str
    name: str
    value: str


@dataclass(frozen=True)
class DerivedValue:
    symbol: str
    name: str
    expression: str


@dataclass(frozen=True)
class SumConstraint:
    """Los parámetros indicados tienen que sumar exactamente `total`."""

    parameters: tuple[str, ...]
    total: Decimal
    label: str


@dataclass(frozen=True)
class TemplateSection:
    heading: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class FormulaDescriptor:
    id: str
    version: int
    name: str
    description: str
    variables: tuple[Variable, ...]
    parameters: tuple[Parameter, ...]
    constants: tuple[Constant, ...]
    derived_values: tuple[DerivedValue, ...]
    constraints: tuple[SumConstraint, ...]
    # Plantilla de la explicación (HU-13). Los `{marcadores}` son claves de parámetros;
    # `{clave:pct}` muestra una fracción como porcentaje.
    explanation_template: tuple[TemplateSection, ...]

    def parameter(self, key: str) -> Parameter | None:
        return next((p for p in self.parameters if p.key == key), None)


PLACEHOLDER_FORMATS = ("", "pct")


def placeholders(descriptor: FormulaDescriptor) -> list[tuple[str, str]]:
    """(clave, formato) de cada marcador de la plantilla, en orden de aparición."""
    found: list[tuple[str, str]] = []
    formatter = string.Formatter()
    for section in descriptor.explanation_template:
        for text in (section.heading, *section.paragraphs):
            for _, field, spec, _ in formatter.parse(text):
                if field is not None:
                    found.append((field, spec or ""))
    return found


def descriptor_problems(descriptor: FormulaDescriptor) -> list[str]:
    """Defectos de un descriptor. Los tests del producto exigen que no haya ninguno."""
    problems: list[str] = []
    keys = [p.key for p in descriptor.parameters]
    if len(set(keys)) != len(keys):
        problems.append("hay claves de parámetro repetidas")
    for p in descriptor.parameters:
        if p.minimum >= p.maximum:
            problems.append(f"{p.key}: rango vacío o invertido")
        elif not p.minimum <= p.default <= p.maximum:
            problems.append(f"{p.key}: el valor por defecto está fuera de sus límites")
    for constraint in descriptor.constraints:
        for key in constraint.parameters:
            if key not in keys:
                problems.append(f"restricción sobre un parámetro inexistente: {key}")
        defaults = [
            p.default for p in descriptor.parameters if p.key in constraint.parameters
        ]
        if sum(defaults) != constraint.total:
            problems.append("los valores por defecto no cumplen una restricción")
    for key, spec in placeholders(descriptor):
        if key not in keys:
            problems.append(f"el marcador {{{key}}} no es un parámetro de la fórmula")
        if spec not in PLACEHOLDER_FORMATS:
            problems.append(
                f"el marcador {{{key}:{spec}}} tiene un formato desconocido"
            )
    return problems


def _p(
    key: str,
    symbol: str,
    name: str,
    unit: str,
    default: str,
    minimum: str,
    maximum: str,
    description: str,
) -> Parameter:
    return Parameter(
        key,
        symbol,
        name,
        unit,
        Decimal(default),
        Decimal(minimum),
        Decimal(maximum),
        description,
    )


SCORING_MODEL_V1 = FormulaDescriptor(
    id="scoring-model",
    version=1,
    name="Modelo de puntaje base",
    description=(
        "Puntaje de 0 a 100 que combina asistencia a partidos, participación institucional, "
        "antigüedad y edad, y un bono para socios nuevos."
    ),
    variables=(
        Variable(
            "asistencia",
            "Asistencia a partidos",
            "Frecuencia de asistencia ponderada por la demanda del partido, más el esfuerzo "
            "de distancia.",
        ),
        Variable(
            "participacion_institucional",
            "Participación institucional",
            "Eventos institucionales y meses de actividades recurrentes de los últimos 365 días.",
        ),
        Variable(
            "antiguedad_edad",
            "Antigüedad y edad",
            "Años ininterrumpidos como socio y edad, contra valores de referencia.",
        ),
        Variable(
            "bono_nuevo_socio",
            "Bono de nuevo socio",
            "Puntos extra que bajan de forma lineal desde el alta.",
        ),
    ),
    parameters=(
        _p(
            "w_a",
            "wA",
            "Peso de la asistencia",
            "",
            "0.60",
            "0",
            "1",
            "Qué parte del puntaje sale de la asistencia a partidos.",
        ),
        _p(
            "w_p",
            "wP",
            "Peso de la participación institucional",
            "",
            "0.20",
            "0",
            "1",
            "Qué parte del puntaje sale de la participación institucional.",
        ),
        _p(
            "w_t",
            "wT",
            "Peso de la antigüedad y edad",
            "",
            "0.20",
            "0",
            "1",
            "Qué parte del puntaje sale de la antigüedad y la edad.",
        ),
        _p(
            "alpha_a",
            "αA",
            "Peso de la distancia dentro de la asistencia",
            "",
            "0.20",
            "0",
            "1",
            "Qué fracción del puntaje de asistencia sale de la distancia al estadio.",
        ),
        _p(
            "d_sat",
            "dsat",
            "Distancia de saturación",
            "km",
            "1200",
            "50",
            "3000",
            "Punto de inflexión de la curva de distancia.",
        ),
        _p(
            "p_inst_max",
            "Pinst_max",
            "Tope de participación institucional",
            "pts",
            "100",
            "1",
            "100",
            "Máximo de puntos de la participación institucional.",
        ),
        _p(
            "alpha_t",
            "αT",
            "Peso de la antigüedad frente a la edad",
            "",
            "0.70",
            "0",
            "1",
            "Qué fracción de este pilar sale de la antigüedad (el resto es la edad).",
        ),
        _p(
            "t_ref",
            "Tref",
            "Antigüedad de referencia",
            "años",
            "50",
            "10",
            "100",
            "Años de antigüedad que dan el máximo de este pilar.",
        ),
        _p(
            "e_ref",
            "Eref",
            "Edad de referencia",
            "años",
            "80",
            "40",
            "120",
            "Edad que da el máximo de este pilar.",
        ),
        _p(
            "gamma",
            "γ",
            "Curvatura",
            "",
            "1.0",
            "0.5",
            "1",
            "Forma de la curva de antigüedad y edad (1 es proporcional).",
        ),
        _p(
            "b_max",
            "Bmax",
            "Bono de bienvenida",
            "pts",
            "15.0",
            "5.0",
            "25.0",
            "Puntos extra el día del alta.",
        ),
        _p(
            "t_max",
            "Tmax",
            "Ventana de extinción del bono",
            "días",
            "180",
            "30",
            "365",
            "Días hasta que el bono llega a cero.",
        ),
        _p(
            "t_carencia",
            "tcarencia",
            "Carencia por reingreso",
            "días",
            "365",
            "0",
            "1095",
            "Días mínimos desde una baja anterior para volver a recibir el bono.",
        ),
    ),
    constants=(
        Constant("C(Clase A)", "Factor de partidos de alta demanda", "1,0"),
        Constant("C(Clase B)", "Factor de partidos regulares de liga", "1,3"),
        Constant("C(Clase C)", "Factor de partidos de baja demanda", "1,8"),
        Constant("Deporte Federado", "Puntos por mes de actividad", "10"),
        Constant("Subcomisiones", "Puntos por mes de actividad", "15"),
        Constant(
            "Vigencia", "Días de vigencia de la participación institucional", "365"
        ),
    ),
    derived_values=(
        DerivedValue("b", "Pendiente de la curva de distancia", "b = 4,356 / dsat"),
    ),
    constraints=(
        SumConstraint(
            ("w_a", "w_p", "w_t"),
            Decimal("1.00"),
            "Los pesos de asistencia, participación institucional y antigüedad y edad",
        ),
    ),
    explanation_template=(
        TemplateSection(
            "Cómo se arma tu puntaje",
            (
                (
                    "Tu puntaje va de 0 a 100 y se arma con tres partes: tu asistencia a los "
                    "partidos ({w_a:pct} del puntaje), tu participación en la vida institucional "
                    "del club ({w_p:pct}) y tu antigüedad y edad ({w_t:pct}). Si sos socio nuevo, "
                    "se suma además un bono de bienvenida. Si el total pasara de 100, se cuenta 100."
                ),
            ),
        ),
        TemplateSection(
            "Asistencia a los partidos ({w_a:pct})",
            (
                (
                    "Cuenta tu asistencia a los partidos del año anterior y de lo que va del año. "
                    "Solo entran los partidos que ya se jugaron y cuya asistencia ya fue cargada: "
                    "un partido sin asistencia cargada no cuenta como ausencia."
                ),
                (
                    "No todos los partidos pesan igual: los de menor demanda pesan más. Un partido "
                    "de Clase A (superclásicos y definiciones de alta demanda) vale 1,0; uno de "
                    "Clase B (partidos regulares de liga) vale 1,3 y uno de Clase C (poca demanda "
                    "o condiciones adversas) vale 1,8. Así el club premia ir a los partidos más "
                    "difíciles de llenar."
                ),
                (
                    "La distancia también suma: {alpha_a:pct} de tu puntaje de asistencia sale de "
                    "la distancia que recorrés hasta el estadio y el resto, de cuántos partidos "
                    "fuiste. Quien vive cerca recibe poco o nada por distancia. Alrededor de los "
                    "{d_sat} km se alcanza un poco más de un tercio del máximo, y a partir del "
                    "doble de esa distancia el crédito es casi total."
                ),
            ),
        ),
        TemplateSection(
            "Participación institucional ({w_p:pct})",
            (
                (
                    "Suma puntos por asistir a elecciones, asambleas y otros eventos "
                    "institucionales o amateur del club (cada evento vale los puntos que el club "
                    "define al publicarlo) y por cada mes de actividad en Deporte Federado (10 "
                    "puntos por mes) o en Subcomisiones (15 puntos por mes, hasta 12 meses por "
                    "actividad)."
                ),
                (
                    "Solo cuenta lo que ocurrió en los últimos 365 días. Esta parte tiene un tope "
                    "de {p_inst_max} puntos."
                ),
            ),
        ),
        TemplateSection(
            "Antigüedad y edad ({w_t:pct})",
            (
                (
                    "Combina tus años ininterrumpidos como socio y tu edad. La antigüedad pesa "
                    "{alpha_t:pct} de esta parte y la edad, el resto. Se compara con una "
                    "referencia de {t_ref} años de antigüedad y {e_ref} años de edad: llegar a esas "
                    "referencias da el máximo de esta parte."
                ),
                (
                    "La curvatura vale {gamma}: con 1, el puntaje crece en proporción directa; con "
                    "un valor menor, quienes están lejos de la referencia reciben proporcionalmente "
                    "más."
                ),
            ),
        ),
        TemplateSection(
            "Bono de nuevo socio",
            (
                (
                    "Quien se asocia recibe hasta {b_max} puntos extra el día del alta. El bono "
                    "baja de forma pareja y llega a cero a los {t_max} días. Si la persona se había "
                    "dado de baja menos de {t_carencia} días antes de volver a asociarse, no recibe "
                    "el bono."
                ),
            ),
        ),
    ),
)

CATALOG: tuple[FormulaDescriptor, ...] = (SCORING_MODEL_V1,)


def get_descriptor(formula_id: str, version: int) -> FormulaDescriptor | None:
    return next(
        (d for d in CATALOG if d.id == formula_id and d.version == version), None
    )

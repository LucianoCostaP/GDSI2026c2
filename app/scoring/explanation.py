"""Explicación del ranking (HU-13): plantilla de la fórmula + valores + bloque común.

Es la única generación del texto: la usan la vista previa del Admin (HU-27) y la vista del
Socio (HU-13), así no pueden diferir (HU-13 FR-008).
"""

import string
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from .catalog import FormulaDescriptor, TemplateSection
from .formatting import format_decimal, format_percent

TITLE = "¿Cómo se calcula mi puntaje?"

# Reglas que comparten todas las fórmulas del catálogo (scoring model, sección 5; HU-13 escenario 8).
COMMON_BLOCK: tuple[TemplateSection, ...] = (
    TemplateSection(
        "Reglas que valen para todos",
        (
            "El puntaje va de 0 a 100 y se redondea a dos decimales.",
            (
                "Solo aparecen en el ranking los socios con la cuota al día. Si la cuota se "
                "atrasa, tu historial de asistencia y participación se conserva: cuando te "
                "pongas al día volvés al ranking con todo lo que acumulaste."
            ),
            (
                "Si dos socios tienen el mismo puntaje, se ordenan por mayor antigüedad; si "
                "siguen empatados, por mayor edad; y si todavía siguen empatados, por menor "
                "número de documento. Esta explicación es la misma para todos los socios del "
                "club y no muestra datos de otros socios."
            ),
        ),
    ),
)


class _Formatter(string.Formatter):
    def format_field(self, value: Any, format_spec: str) -> str:
        if format_spec == "pct":
            return format_percent(value)
        if format_spec == "":
            return format_decimal(value)
        raise ValueError(f"formato desconocido: {format_spec}")


_formatter = _Formatter()


@dataclass(frozen=True)
class ExplanationSection:
    heading: str
    paragraphs: tuple[str, ...]


@dataclass(frozen=True)
class ExplanationBlock:
    id: str
    sections: tuple[ExplanationSection, ...]


@dataclass(frozen=True)
class RankingExplanation:
    title: str
    blocks: tuple[ExplanationBlock, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _render(
    sections: tuple[TemplateSection, ...], values: Mapping[str, Decimal]
) -> tuple[ExplanationSection, ...]:
    return tuple(
        ExplanationSection(
            _formatter.vformat(s.heading, (), values),
            tuple(_formatter.vformat(p, (), values) for p in s.paragraphs),
        )
        for s in sections
    )


def render_explanation(
    descriptor: FormulaDescriptor, values: Mapping[str, Decimal]
) -> RankingExplanation:
    """Genera la explicación. `values` tiene que traer todos los parámetros ya validados."""
    return RankingExplanation(
        TITLE,
        (
            ExplanationBlock(
                "formula", _render(descriptor.explanation_template, values)
            ),
            ExplanationBlock("common", _render(COMMON_BLOCK, values)),
        ),
    )

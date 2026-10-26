"""Catálogo, validación y explicación de la fórmula (HU-27, FR-003 y FR-004)."""

import dataclasses
from decimal import Decimal

import pytest

from app.scoring.catalog import (
    CATALOG,
    SCORING_MODEL_V1,
    Parameter,
    TemplateSection,
    descriptor_problems,
    get_descriptor,
)
from app.scoring.explanation import render_explanation
from app.scoring.formatting import decimal_to_str, format_decimal, format_percent
from app.scoring.validation import (
    MISSING,
    NOT_A_NUMBER,
    OUT_OF_LIMITS,
    SUM_VIOLATED,
    UNKNOWN,
    parse_decimal,
    validate_values,
)

DEFAULTS = {p.key: decimal_to_str(p.default) for p in SCORING_MODEL_V1.parameters}


def codes(raw: dict) -> list[tuple[str, str | None]]:
    result = validate_values(SCORING_MODEL_V1, raw)
    return [(v.code, v.parameter) for v in result.violations]


@pytest.mark.parametrize("descriptor", CATALOG, ids=lambda d: f"{d.id}-v{d.version}")
def test_every_descriptor_of_the_catalog_is_consistent(descriptor) -> None:
    assert descriptor_problems(descriptor) == []


def test_descriptor_with_default_outside_limits_is_detected() -> None:
    broken = dataclasses.replace(
        SCORING_MODEL_V1,
        parameters=(
            dataclasses.replace(SCORING_MODEL_V1.parameters[0], default=Decimal(2)),
            *SCORING_MODEL_V1.parameters[1:],
        ),
    )
    assert any("fuera de sus límites" in p for p in descriptor_problems(broken))


def test_descriptor_with_empty_or_inverted_range_is_detected() -> None:
    inverted = Parameter(
        "x", "x", "X", "", Decimal(1), Decimal(5), Decimal(1), "rango invertido"
    )
    broken = dataclasses.replace(
        SCORING_MODEL_V1, parameters=(*SCORING_MODEL_V1.parameters, inverted)
    )
    assert any("rango vacío o invertido" in p for p in descriptor_problems(broken))


def test_descriptor_with_placeholder_that_is_not_a_parameter_is_detected() -> None:
    broken = dataclasses.replace(
        SCORING_MODEL_V1,
        explanation_template=(TemplateSection("Título {no_existe}", ("Texto",)),),
    )
    assert any("no_existe" in p for p in descriptor_problems(broken))


def test_the_text_mentions_the_constants_of_the_formula() -> None:
    text = " ".join(
        p for s in SCORING_MODEL_V1.explanation_template for p in s.paragraphs
    )
    for constant in SCORING_MODEL_V1.constants:
        if constant.symbol.startswith("C("):
            assert constant.value in text


def test_get_descriptor_finds_by_id_and_version() -> None:
    assert get_descriptor("scoring-model", 1) is SCORING_MODEL_V1
    assert get_descriptor("scoring-model", 2) is None
    assert get_descriptor("otra", 1) is None


def test_defaults_are_valid() -> None:
    result = validate_values(SCORING_MODEL_V1, DEFAULTS)
    assert result.valid
    assert result.values["w_a"] == Decimal("0.60")


def test_missing_parameter_is_reported_and_never_completed() -> None:
    raw = {k: v for k, v in DEFAULTS.items() if k != "gamma"}
    assert codes(raw) == [(MISSING, "gamma")]
    assert validate_values(SCORING_MODEL_V1, raw).values == {}


def test_blank_value_counts_as_missing() -> None:
    assert codes({**DEFAULTS, "t_ref": "  "}) == [(MISSING, "t_ref")]


def test_limits_are_inclusive() -> None:
    assert validate_values(SCORING_MODEL_V1, {**DEFAULTS, "d_sat": "50"}).valid
    assert validate_values(SCORING_MODEL_V1, {**DEFAULTS, "d_sat": "3000"}).valid
    assert codes({**DEFAULTS, "d_sat": "49.99"}) == [(OUT_OF_LIMITS, "d_sat")]
    assert codes({**DEFAULTS, "d_sat": "3000.01"}) == [(OUT_OF_LIMITS, "d_sat")]


def test_limit_message_names_the_parameter_and_its_limits() -> None:
    result = validate_values(SCORING_MODEL_V1, {**DEFAULTS, "d_sat": "10"})
    assert result.violations[0].message == (
        "«Distancia de saturación» tiene que estar entre 50 y 3000 km."
    )


def test_sum_violation_shows_the_sum_that_fails() -> None:
    result = validate_values(
        SCORING_MODEL_V1, {**DEFAULTS, "w_a": "0.5", "w_p": "0.2", "w_t": "0.2"}
    )
    assert [v.code for v in result.violations] == [SUM_VIOLATED]
    assert "hoy suman 0,9" in result.violations[0].message


def test_sum_is_exact_in_decimal_arithmetic() -> None:
    # En coma flotante binaria 0.1 + 0.2 + 0.7 no da 1.
    raw = {**DEFAULTS, "w_a": "0.1", "w_p": "0.2", "w_t": "0.7"}
    assert validate_values(SCORING_MODEL_V1, raw).valid
    assert validate_values(
        SCORING_MODEL_V1, {**raw, "w_a": 0.1, "w_p": 0.2, "w_t": 0.7}
    ).valid


def test_limit_and_sum_violations_are_reported_together() -> None:
    assert codes({**DEFAULTS, "w_a": "1.5"}) == [
        (OUT_OF_LIMITS, "w_a"),
        (SUM_VIOLATED, None),
    ]


def test_unknown_parameters_are_rejected() -> None:
    assert codes({**DEFAULTS, "extra": "1"}) == [(UNKNOWN, "extra")]


@pytest.mark.parametrize("bad", ["abc", True, [1], {"a": 1}, "NaN", "Infinity"])
def test_values_that_are_not_finite_numbers_are_rejected(bad) -> None:
    assert codes({**DEFAULTS, "gamma": bad}) == [(NOT_A_NUMBER, "gamma")]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(1, "1"), ("0,6", "0.6"), ("0.60", "0.60"), (0.6, "0.6"), (Decimal(2), "2")],
)
def test_parse_decimal_accepts_numbers_and_numeric_text(raw, expected) -> None:
    assert parse_decimal(raw) == Decimal(expected)


def test_number_formatting_uses_decimal_comma() -> None:
    assert format_decimal(Decimal("0.20")) == "0,2"
    assert format_decimal(Decimal(1200)) == "1200"
    assert format_decimal(Decimal("1E+2")) == "100"
    assert format_percent(Decimal("0.60")) == "60 %"
    assert format_percent(Decimal("0.125")) == "12,5 %"
    assert decimal_to_str(Decimal("0.600")) == "0.6"


def test_explanation_shows_the_values_entered() -> None:
    values = validate_values(
        SCORING_MODEL_V1,
        {**DEFAULTS, "w_a": "0.5", "w_p": "0.3", "d_sat": "900", "b_max": "20"},
    ).values
    explanation = render_explanation(SCORING_MODEL_V1, values).to_dict()
    text = " ".join(
        p
        for block in explanation["blocks"]
        for section in block["sections"]
        for p in section["paragraphs"]
    )
    assert "50 % del puntaje" in text
    assert "900 km" in text
    assert "hasta 20 puntos" in text
    assert "{" not in text


def test_explanation_has_formula_and_common_blocks() -> None:
    values = validate_values(SCORING_MODEL_V1, DEFAULTS).values
    explanation = render_explanation(SCORING_MODEL_V1, values)
    assert [b.id for b in explanation.blocks] == ["formula", "common"]
    assert explanation.title == "¿Cómo se calcula mi puntaje?"

"""HU-25, Ciclo 0: motor de scoring puro (sin base de datos ni HTTP)."""

import ast
import inspect
from dataclasses import replace
from decimal import Decimal, getcontext

import pytest

from app.scoring import engine
from app.scoring.components import COMPONENT_KEYS, total_of
from app.scoring.engine import (
    ScoringInputs,
    ScoringParameters,
    calculate_score,
    distance_score,
    frequency_score,
    new_member_bonus,
    round_component,
)
from tests.scoring_reference import (
    REFERENCE_COMPONENTS,
    REFERENCE_INPUTS,
    REFERENCE_TOTAL,
)

PARAMS = ScoringParameters.defaults()
NONE = {"A": 0, "B": 0, "C": 0}


def d(value: str) -> Decimal:
    return Decimal(value)


def inputs(**overrides) -> ScoringInputs:
    """Socio sin actividad, veterano (sin bono), sobre el que cada test cambia lo suyo."""
    base = ScoringInputs(
        matches_by_class=dict(NONE),
        attended_by_class=dict(NONE),
        distance_km=d("0"),
        institutional_points=d("0"),
        seniority_years=d("0"),
        age_years=d("0"),
        days_since_alta=3650,
    )
    return replace(base, **overrides)


def components_of(socio: ScoringInputs, params: ScoringParameters = PARAMS):
    return calculate_score(socio, params).components


# --- Dataset de referencia -----------------------------------------------------------------


def test_reference_dataset_gives_59_55() -> None:
    result = calculate_score(REFERENCE_INPUTS, PARAMS)

    assert result.components == REFERENCE_COMPONENTS
    assert result.total == REFERENCE_TOTAL


def test_reference_components_use_the_documented_keys() -> None:
    result = calculate_score(REFERENCE_INPUTS, PARAMS)

    assert set(result.components) == set(COMPONENT_KEYS)


# --- Frecuencia ponderada por clase --------------------------------------------------------


def test_frequency_weighted_by_class() -> None:
    matches = {"A": 4, "B": 10, "C": 6}
    attended = {"A": 3, "B": 6, "C": 5}

    # 100 · (3·1,0 + 6·1,3 + 5·1,8) / (4·1,0 + 10·1,3 + 6·1,8) = 100 · 19,8 / 27,8
    pillar = frequency_score(matches, attended)

    assert round_component(pillar) == d("71.22")


def test_a_class_c_match_weighs_more_than_a_class_a_match() -> None:
    matches = {"A": 1, "B": 0, "C": 1}

    went_to_c = frequency_score(matches, {"A": 0, "B": 0, "C": 1})
    went_to_a = frequency_score(matches, {"A": 1, "B": 0, "C": 0})

    assert went_to_c > went_to_a


def test_frequency_with_no_matches_in_the_denominator_is_zero() -> None:
    assert frequency_score(NONE, NONE) == 0
    assert components_of(inputs())["attendance_frequency"] == d("0.00")


def test_attending_every_match_gives_the_full_frequency_component() -> None:
    all_matches = {"A": 2, "B": 3, "C": 1}

    socio = inputs(matches_by_class=all_matches, attended_by_class=all_matches)

    # wA · (1 − αA) · 100 = 0,60 · 0,80 · 100
    assert components_of(socio)["attendance_frequency"] == d("48.00")


# --- Distancia (Gompertz) ------------------------------------------------------------------


def test_distance_gompertz_at_dsat_is_36_79() -> None:
    pillar = distance_score(d("1200"), 1, d("1200"))

    assert round_component(pillar) == d("36.79")


@pytest.mark.parametrize(
    ("times_dsat", "expected"),
    [("0", "0.00"), ("1.68", "94.96"), ("2", "98.73")],
)
def test_distance_curve_shape(times_dsat: str, expected: str) -> None:
    dsat = d("1200")

    pillar = distance_score(dsat * d(times_dsat), 1, dsat)

    assert round_component(pillar) == d(expected)


def test_distance_gompertz_no_attended_is_zero() -> None:
    assert distance_score(d("1200"), 0, d("1200")) == 0
    far_but_never_attended = inputs(distance_km=d("3000"))
    assert components_of(far_but_never_attended)["attendance_distance"] == d("0.00")


def test_distance_grows_with_the_distance() -> None:
    dsat = d("1200")

    values = [distance_score(d(km), 1, dsat) for km in ("50", "600", "1200", "2400")]

    assert values == sorted(values)


def test_distance_component_uses_alpha_a_of_the_attendance_weight() -> None:
    socio = inputs(
        matches_by_class={"A": 1, "B": 0, "C": 0},
        attended_by_class={"A": 1, "B": 0, "C": 0},
        distance_km=d("1200"),
    )

    # wA · αA · 36,7879... = 0,60 · 0,20 · 36,79
    assert components_of(socio)["attendance_distance"] == d("4.41")


# --- Participación institucional -----------------------------------------------------------


def test_institutional_capped_by_pinst_max() -> None:
    under_the_cap = components_of(inputs(institutional_points=d("70")))
    over_the_cap = components_of(inputs(institutional_points=d("150")))
    lower_cap = components_of(
        inputs(institutional_points=d("150")), replace(PARAMS, p_inst_max=d("50"))
    )

    assert under_the_cap["institutional"] == d("14.00")  # 0,20 · 70
    assert over_the_cap["institutional"] == d("20.00")  # 0,20 · min(100, 150)
    assert lower_cap["institutional"] == d("10.00")  # 0,20 · min(50, 150)


# --- Antigüedad y edad ---------------------------------------------------------------------


def test_seniority_age_pillar() -> None:
    socio = inputs(seniority_years=d("10"), age_years=d("45"))

    # (0,7·10 + 0,3·45) / (0,7·50 + 0,3·80) = 20,5 / 59 = 0,3475 → 0,20 · 34,75
    assert components_of(socio)["seniority_age"] == d("6.95")


def test_seniority_age_is_capped_at_the_reference_values() -> None:
    at_reference = inputs(seniority_years=d("50"), age_years=d("80"))
    beyond = inputs(seniority_years=d("90"), age_years=d("100"))

    assert components_of(at_reference)["seniority_age"] == d("20.00")
    assert components_of(beyond)["seniority_age"] == d("20.00")


def test_gamma_below_one_favours_those_far_from_the_reference() -> None:
    socio = inputs(seniority_years=d("10"), age_years=d("45"))

    curved = components_of(socio, replace(PARAMS, gamma=d("0.5")))

    # 0,3475^0,5 = 0,5895 → 0,20 · 58,95
    assert curved["seniority_age"] == d("11.79")
    assert curved["seniority_age"] > components_of(socio)["seniority_age"]


def test_a_socio_with_no_seniority_and_no_age_scores_zero_here() -> None:
    assert components_of(inputs())["seniority_age"] == d("0.00")


# --- Bono de nuevo socio -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days", "expected"),
    [(0, "15.00"), (90, "7.50"), (179, "0.08"), (180, "0.00"), (181, "0.00")],
)
def test_new_member_bonus_linear(days: int, expected: str) -> None:
    socio = inputs(days_since_alta=days)

    assert components_of(socio)["new_member_bonus"] == d(expected)


@pytest.mark.parametrize(
    ("days_since_baja", "expected"),
    [(None, "15.00"), (365, "15.00"), (364, "0.00"), (0, "0.00")],
)
def test_new_member_bonus_zero_with_recent_baja(
    days_since_baja: int | None, expected: str
) -> None:
    # tcarencia = 365: solo una baja a menos de 365 días del alta quita el bono.
    socio = inputs(days_since_alta=0, days_since_previous_baja=days_since_baja)

    assert components_of(socio)["new_member_bonus"] == d(expected)


def test_new_member_bonus_function_is_never_negative() -> None:
    assert new_member_bonus(10_000, None, PARAMS) == 0


# --- Tope de 100 ---------------------------------------------------------------------------


def test_cap_adjustment_keeps_total_100() -> None:
    perfect = {"A": 1, "B": 1, "C": 1}
    params = replace(PARAMS, d_sat=d("50"))  # a 1000 km la distancia ya satura
    socio = inputs(
        matches_by_class=perfect,
        attended_by_class=perfect,
        distance_km=d("1000"),
        institutional_points=d("100"),
        seniority_years=d("100"),
        age_years=d("100"),
        days_since_alta=0,
    )

    result = calculate_score(socio, params)

    # 48 + 12 + 20 + 20 + 15 de bono = 115 → ajuste de −15.
    assert result.components["new_member_bonus"] == d("15.00")
    assert result.components["cap_adjustment"] == d("-15.00")
    assert result.total == d("100.00")


def test_no_cap_adjustment_when_the_sum_is_exactly_100() -> None:
    perfect = {"A": 1, "B": 1, "C": 1}
    params = replace(PARAMS, d_sat=d("50"))
    socio = inputs(
        matches_by_class=perfect,
        attended_by_class=perfect,
        distance_km=d("1000"),
        institutional_points=d("100"),
        seniority_years=d("100"),
        age_years=d("100"),
    )

    result = calculate_score(socio, params)

    assert result.components["cap_adjustment"] == d("0.00")
    assert result.total == d("100.00")


# --- Redondeo y total ----------------------------------------------------------------------


def test_components_rounded_half_up_and_total_is_sum() -> None:
    # 0,50 · 0,05 = 0,025: mitad hacia arriba da 0,03 (mitad par daría 0,02).
    params = replace(PARAMS, w_p=d("0.50"))
    socio = inputs(institutional_points=d("0.05"))

    result = calculate_score(socio, params)

    assert result.components["institutional"] == d("0.03")
    assert round_component(d("0.015")) == d("0.02")
    assert round_component(d("0.014999")) == d("0.01")
    assert result.total == sum(result.components.values(), d("0.00"))
    assert result.total == total_of(result.components)


def test_every_component_has_exactly_two_decimals() -> None:
    result = calculate_score(REFERENCE_INPUTS, PARAMS)

    assert all(v.as_tuple().exponent == -2 for v in result.components.values())
    assert result.total.as_tuple().exponent == -2


@pytest.mark.parametrize("days", [0, 45, 400])
@pytest.mark.parametrize("attended", [0, 3, 6])
@pytest.mark.parametrize("points", ["0", "55", "400"])
def test_total_is_always_between_0_and_100(
    days: int, attended: int, points: str
) -> None:
    socio = inputs(
        matches_by_class={"A": 2, "B": 6, "C": 2},
        attended_by_class={"A": min(attended, 2), "B": attended, "C": min(attended, 2)},
        distance_km=d("800"),
        institutional_points=d(points),
        seniority_years=d("30"),
        age_years=d("60"),
        days_since_alta=days,
    )

    assert 0 <= calculate_score(socio, PARAMS).total <= 100


# --- Aritmética decimal --------------------------------------------------------------------


def test_uses_decimal_not_float() -> None:
    result = calculate_score(REFERENCE_INPUTS, PARAMS)

    assert all(isinstance(v, Decimal) for v in result.components.values())
    assert isinstance(result.total, Decimal)
    tree = ast.parse(inspect.getsource(engine))
    uses_float = any(
        isinstance(node, ast.Name) and node.id == "float" for node in ast.walk(tree)
    ) or any(
        isinstance(node, ast.Constant) and isinstance(node.value, float)
        for node in ast.walk(tree)
    )
    assert not uses_float


def test_result_does_not_depend_on_the_global_decimal_context() -> None:
    expected = calculate_score(REFERENCE_INPUTS, PARAMS)
    previous = getcontext().prec
    getcontext().prec = 5
    try:
        under_a_poor_context = calculate_score(REFERENCE_INPUTS, PARAMS)
    finally:
        getcontext().prec = previous

    assert under_a_poor_context == expected


def test_the_calculation_is_deterministic() -> None:
    assert calculate_score(REFERENCE_INPUTS, PARAMS) == calculate_score(
        REFERENCE_INPUTS, PARAMS
    )


# --- Parámetros ----------------------------------------------------------------------------


def test_defaults_are_the_catalog_defaults() -> None:
    assert PARAMS.w_a == d("0.60")
    assert PARAMS.d_sat == d("1200")
    assert PARAMS.t_carencia == d("365")
    assert PARAMS.w_a + PARAMS.w_p + PARAMS.w_t == d("1.00")


def test_parameters_are_built_from_the_text_values_of_a_rules_version() -> None:
    # `RulesVersion.values` guarda los decimales como texto.
    published = {
        "w_a": "0.60",
        "w_p": "0.20",
        "w_t": "0.20",
        "alpha_a": "0.20",
        "d_sat": "1200",
        "p_inst_max": "100",
        "alpha_t": "0.70",
        "t_ref": "50",
        "e_ref": "80",
        "gamma": "1.0",
        "b_max": "15.0",
        "t_max": "180",
        "t_carencia": "365",
    }

    assert ScoringParameters.from_values(published) == PARAMS


def test_parameters_reject_missing_unknown_and_non_numeric_values() -> None:
    published = {
        f: str(getattr(PARAMS, f)) for f in ScoringParameters.__dataclass_fields__
    }

    with pytest.raises(ValueError):
        ScoringParameters.from_values(
            {k: v for k, v in published.items() if k != "w_a"}
        )
    with pytest.raises(ValueError):
        ScoringParameters.from_values({**published, "extra": "1"})
    with pytest.raises(ValueError):
        ScoringParameters.from_values({**published, "w_a": "mucho"})


@pytest.mark.parametrize("name", ["d_sat", "t_ref", "e_ref", "t_max"])
def test_parameters_that_divide_must_be_positive(name: str) -> None:
    with pytest.raises(ValueError):
        replace(PARAMS, **{name: d("0")})


# --- Validación de insumos -----------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"matches_by_class": {"A": 1, "B": 1}},
        {"attended_by_class": {"A": 1, "B": 0, "C": 0}},  # más asistidos que partidos
        {"matches_by_class": {"A": -1, "B": 0, "C": 0}},
        {"distance_km": d("-1")},
        {"institutional_points": d("-1")},
        {"seniority_years": d("-1")},
        {"age_years": d("-1")},
        {"days_since_alta": -1},
        {"days_since_previous_baja": -1},
    ],
    ids=[
        "missing_class",
        "attended_over_matches",
        "negative_matches",
        "negative_distance",
        "negative_points",
        "negative_seniority",
        "negative_age",
        "negative_days_since_alta",
        "negative_days_since_baja",
    ],
)
def test_inconsistent_inputs_are_rejected(overrides: dict) -> None:
    with pytest.raises(ValueError):
        inputs(**overrides)

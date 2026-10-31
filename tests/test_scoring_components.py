"""Componentes del puntaje y su suma (HU-25, modelo de scoring regla 3)."""

from decimal import Decimal

import pytest

from app.scoring.components import COMPONENT_KEYS, empty_components, total_of


def test_the_six_components_are_the_ones_the_scoring_model_defines() -> None:
    assert COMPONENT_KEYS == (
        "attendance_frequency",
        "attendance_distance",
        "institutional",
        "seniority_age",
        "new_member_bonus",
        "cap_adjustment",
    )


def test_empty_components_are_all_zero_with_two_decimals() -> None:
    components = empty_components()

    assert set(components) == set(COMPONENT_KEYS)
    assert all(value == Decimal("0.00") for value in components.values())
    assert all(value.as_tuple().exponent == -2 for value in components.values())


def test_empty_components_returns_a_new_dict_each_time() -> None:
    first = empty_components()
    first["institutional"] = Decimal("5.00")

    assert empty_components()["institutional"] == Decimal("0.00")


def test_total_of_empty_components_is_zero() -> None:
    assert total_of(empty_components()) == Decimal("0.00")


def test_total_is_the_sum_of_the_components_including_the_cap_adjustment() -> None:
    components = empty_components() | {
        "attendance_frequency": Decimal("80.00"),
        "attendance_distance": Decimal("25.00"),
        "cap_adjustment": Decimal("-5.00"),
    }

    assert total_of(components) == Decimal("100.00")


@pytest.mark.parametrize("missing", COMPONENT_KEYS)
def test_total_rejects_a_missing_component(missing: str) -> None:
    components = empty_components()
    del components[missing]

    with pytest.raises(ValueError):
        total_of(components)


def test_total_rejects_an_unknown_component() -> None:
    components = empty_components() | {"bonus_extra": Decimal("1.00")}

    with pytest.raises(ValueError):
        total_of(components)

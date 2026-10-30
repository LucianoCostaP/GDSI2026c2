"""HU-25, Ciclo 3c: instantánea de entradas y su paso al motor (módulo puro)."""

import json
from datetime import date
from decimal import Decimal

import pytest

from app.scoring.attendance_inputs import MatchEvent, build_attendance_inputs
from app.scoring.engine import ScoringParameters, calculate_score
from app.scoring.institutional_inputs import (
    ActivityRecord,
    InstitutionalEvent,
    build_institutional_inputs,
)
from app.scoring.membership_inputs import build_membership_inputs
from app.scoring.snapshot import build_scoring_inputs, scoring_inputs_from_snapshot
from tests.scoring_reference import (
    REFERENCE_COMPONENTS,
    REFERENCE_INPUTS,
    REFERENCE_TOTAL,
)

PARAMS = ScoringParameters.defaults()
CALCULATION_DATE = date(2026, 10, 29)


def real_inputs():
    """Los tres grupos de insumos de un socio con actividad, armados como en el ranking."""
    attendance = build_attendance_inputs(
        alta=date(2015, 3, 1),
        distance_km=Decimal("350.50"),
        calculation_date=CALCULATION_DATE,
        events=[
            MatchEvent("P1", date(2026, 3, 1), "A"),
            MatchEvent("P2", date(2026, 4, 1), "B"),
            MatchEvent("P3", date(2026, 5, 1), "C"),
        ],
        attended_event_ids={"P1", "P3"},
    )
    institutional = build_institutional_inputs(
        calculation_date=CALCULATION_DATE,
        attended_events=[InstitutionalEvent("ASAMBLEA", date(2026, 9, 1), 40)],
        activities=[ActivityRecord("subcomision", date(2026, 5, 1), date(2026, 7, 31))],
    )
    membership = build_membership_inputs(
        birth_date=date(1980, 1, 1),
        alta=date(2015, 3, 1),
        previous_baja=date(2014, 1, 1),
        calculation_date=CALCULATION_DATE,
    )
    return attendance, institutional, membership


def test_build_scoring_inputs_maps_each_group_to_the_engine() -> None:
    attendance, institutional, membership = real_inputs()

    inputs = build_scoring_inputs(attendance, institutional, membership)

    assert inputs.matches_by_class == {"A": 1, "B": 1, "C": 1}
    assert inputs.attended_by_class == {"A": 1, "B": 0, "C": 1}
    assert inputs.distance_km == Decimal("350.50")
    assert inputs.institutional_points == Decimal(85)  # 40 + 3 meses · 15
    assert inputs.seniority_years == Decimal(11)
    assert inputs.age_years == Decimal(46)
    assert inputs.days_since_alta == membership.days_since_alta
    assert inputs.days_since_previous_baja == 424


def test_the_reference_snapshot_gives_59_55() -> None:
    snapshot = {
        "attendance": {
            "matches_by_class": {"A": 4, "B": 10, "C": 6},
            "attended_by_class": {"A": 3, "B": 6, "C": 5},
            "distance_km": "1200",
        },
        "institutional": {"points": 70},
        "membership": {
            "seniority_years": 10,
            "age_years": 45,
            "days_since_alta": 3650,
            "days_between_previous_baja_and_alta": None,
        },
    }

    inputs = scoring_inputs_from_snapshot(snapshot)
    result = calculate_score(inputs, PARAMS)

    assert inputs == REFERENCE_INPUTS
    assert result.components == REFERENCE_COMPONENTS
    assert result.total == REFERENCE_TOTAL


def test_a_snapshot_stored_as_json_rebuilds_the_same_inputs_and_score() -> None:
    attendance, institutional, membership = real_inputs()
    snapshot = {
        "attendance": attendance.as_dict(),
        "institutional": institutional.as_dict(),
        "membership": membership.as_dict(),
    }

    stored = json.loads(json.dumps(snapshot))

    rebuilt = scoring_inputs_from_snapshot(stored)
    original = build_scoring_inputs(attendance, institutional, membership)
    assert rebuilt == original
    assert calculate_score(rebuilt, PARAMS) == calculate_score(original, PARAMS)


def test_the_same_snapshot_and_rules_give_the_same_score_every_time() -> None:
    attendance, institutional, membership = real_inputs()
    inputs = build_scoring_inputs(attendance, institutional, membership)

    results = [calculate_score(inputs, PARAMS) for _ in range(3)]

    assert results[0] == results[1] == results[2]


def test_a_snapshot_missing_a_group_is_rejected() -> None:
    with pytest.raises(KeyError):
        scoring_inputs_from_snapshot({"attendance": {}, "institutional": {}})
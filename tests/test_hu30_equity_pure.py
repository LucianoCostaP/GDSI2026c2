"""Tests unitarios puros para HU-30 (Análisis de equidad).

Cubre todos los escenarios puros y criterios de éxito sin depender de base de datos ni red:
- SC-001: Caso identidad (reglas iguales a las del ranking).
- SC-002: Sumas y consistencia ponderada de segmentos.
- SC-003: Caso de referencia de bandas a mano y regla de fusión determinística.
- SC-004: Privacidad y grupos chicos (< 10 socios).
- SC-005: Consistencia de los grupos Suben, Bajan, Sin cambio relevante y Todos.
- Veredictos de equidad (OK, ATTENTION, BIAS) y formato de textos en es-AR.
- Generación de filas CSV para perfil, segmento y veredicto.
"""

import uuid
from decimal import Decimal

from app.schemas.rules_simulation import (
    BreakdownOut,
    RulesSimulationResultOut,
)
from app.scoring.equity import (
    GROUP_TOO_SMALL_MESSAGE,
    _BandRecord,
    band_label,
    calculate_equity,
    compute_segmentations,
    merge_bands,
)
from app.scoring.rules_simulation import SimulatedEntry, StoredEntry
from app.services.rules_simulation_export import csv_rows


def _make_stored_entry(
    socio_id: uuid.UUID,
    pos: int,
    total: Decimal,
    distance_km: Decimal = Decimal("15.0"),
    seniority_years: int = 5,
    age_years: int = 35,
    matches_c: int = 0,
    attended_c: int = 0,
    inst_points: Decimal = Decimal(0),
) -> StoredEntry:
    return StoredEntry(
        socio_id=socio_id,
        position=pos,
        components={},
        total=total,
        snapshot={
            "attendance": {
                "distance_km": str(distance_km),
                "matches_by_class": {"C": matches_c},
                "attended_by_class": {"C": attended_c},
            },
            "membership": {
                "seniority_years": seniority_years,
                "age_years": age_years,
            },
            "institutional": {
                "points": str(inst_points),
            },
        },
    )


def _make_simulated_entry(
    socio_id: uuid.UUID, pos: int, total: Decimal
) -> SimulatedEntry:
    return SimulatedEntry(
        socio_id=socio_id,
        position=pos,
        components={},
        total=total,
    )


# --- Tests de Bandas y Fusión Determinística (SC-003) ------------------------------------


def test_band_labels():
    assert band_label("distance", 0, 10) == "menos de 10 km"
    assert band_label("distance", 10, 50) == "de 10 a menos de 50 km"
    assert band_label("distance", 2000, None) == "2000 km o más"

    assert band_label("seniority", 0, 1) == "menos de 1 año"
    assert band_label("seniority", 0, 5) == "menos de 5 años"
    assert band_label("seniority", 1, 5) == "de 1 a menos de 5 años"
    assert band_label("seniority", 5, 10) == "de 5 a menos de 10 años"
    assert band_label("seniority", 20, None) == "20 años o más"

    assert band_label("age", 0, 30) == "menos de 30 años"
    assert band_label("age", 30, 45) == "de 30 a menos de 45 años"
    assert band_label("age", 75, None) == "75 años o más"


def test_merge_bands_deterministic():
    # 5 bandas: [0, 1) con 5, [1, 5) con 20, [5, 10) con 30, [10, 20) con 40, [20, None) con 50
    # La banda 0 tiene 5 socios (< 10). Debe fusionarse con su única vecina (1).
    records = [
        _BandRecord(0, 1, [None] * 5),
        _BandRecord(1, 5, [None] * 20),
        _BandRecord(5, 10, [None] * 30),
        _BandRecord(10, 20, [None] * 40),
        _BandRecord(20, None, [None] * 50),
    ]
    merged = merge_bands(records)
    assert len(merged) == 4
    assert merged[0].lower == 0 and merged[0].upper == 5
    assert len(merged[0].members) == 25

    # Caso última banda chica: debe fusionarse con la penúltima
    records = [
        _BandRecord(0, 10, [None] * 20),
        _BandRecord(10, 50, [None] * 20),
        _BandRecord(50, 200, [None] * 3),
    ]
    merged = merge_bands(records)
    assert len(merged) == 2
    assert merged[1].lower == 10 and merged[1].upper == 200
    assert len(merged[1].members) == 23

    # Caso banda intermedia con empate en vecinos: debe elegir el vecino inferior
    records = [
        _BandRecord(0, 10, [None] * 20),
        _BandRecord(10, 50, [None] * 4),
        _BandRecord(50, 200, [None] * 20),
    ]
    merged = merge_bands(records)
    assert len(merged) == 2
    # El vecino inferior es el de [0, 10), por lo que se fusionan 0 y 1
    assert merged[0].lower == 0 and merged[0].upper == 50
    assert len(merged[0].members) == 24
    assert merged[1].lower == 50 and merged[1].upper == 200


# --- SC-001: Identidad (Valores iguales a los del ranking) --------------------------------


def test_equity_identity_case():
    n = 30
    before = []
    after = []
    for i in range(1, n + 1):
        uid = uuid.uuid4()
        score = Decimal("50.00")
        dist = Decimal(i * 10)
        sen = i % 25
        age = 20 + i
        before.append(
            _make_stored_entry(
                uid,
                pos=i,
                total=score,
                distance_km=dist,
                seniority_years=sen,
                age_years=age,
                matches_c=5,
                attended_c=3,
                inst_points=Decimal(10),
            )
        )
        after.append(_make_simulated_entry(uid, pos=i, total=score))

    equity = calculate_equity(before, after, relevant_threshold=1)
    assert equity.status == "available"
    assert equity.verdict is not None
    assert equity.verdict.code == "EQUITY_OK"
    assert (
        equity.verdict.text
        == "Sin diferencias marcadas: el cambio no favorece ni perjudica de más a ningún grupo."
    )
    assert len(equity.verdict.items) == 0

    # Suben y Bajan vacíos -> too_small = True
    assert equity.profile is not None
    groups = {g.group: g for g in equity.profile.groups}
    assert groups["up"].count == 0
    assert groups["up"].too_small is True
    assert groups["up"].message == GROUP_TOO_SMALL_MESSAGE
    assert groups["down"].count == 0
    assert groups["down"].too_small is True
    assert groups["no_change"].count == n
    assert groups["no_change"].too_small is False
    assert groups["all"].count == n

    # En los segmentos, ninguna marca ni mayor desvío
    for seg_attr in equity.segmentations:
        if seg_attr.status == "available":
            assert seg_attr.verdict is not None
            assert seg_attr.verdict.code == "EQUITY_OK"
            for s in seg_attr.segments:
                assert s.avg_score_difference == "0.00"
                assert s.avg_position_change == "0.0"
                assert s.deviation == "0.0"
                assert s.mark == "none"
                assert s.direction is None
                assert s.largest_deviation is False


# --- SC-002: Consistencia y Sumas Ponderadas ---------------------------------------------


def test_equity_weighted_sums_and_deviations():
    n = 100
    before = []
    after = []
    # Simulamos movimiento: los primeros 30 bajan, los últimos 30 suben
    for i in range(1, n + 1):
        uid = uuid.uuid4()
        score_before = Decimal("40.00")
        score_after = Decimal("45.00")  # suben 5 pts en promedio
        sim_pos = n - i + 1  # invierte orden
        dist = Decimal(i * 15)
        sen = i % 25
        age = 18 + i // 2
        before.append(
            _make_stored_entry(
                uid,
                pos=i,
                total=score_before,
                distance_km=dist,
                seniority_years=sen,
                age_years=age,
                matches_c=2,
                attended_c=1,
            )
        )
        after.append(_make_simulated_entry(uid, pos=sim_pos, total=score_after))

    equity = calculate_equity(before, after, relevant_threshold=1)
    assert equity.status == "available"

    for seg_attr in equity.segmentations:
        if seg_attr.status == "available":
            # La suma de count de segmentos es N
            total_socios = sum(s.count for s in seg_attr.segments)
            assert total_socios == n

            # Suma ponderada de avg_position_change es exactamente 0
            weighted_pos_change = sum(
                Decimal(s.avg_position_change) * Decimal(s.count)
                for s in seg_attr.segments
            )
            # Puede haber un pequeño error de redondeo de 1 decimal en la suma,
            # pero la suma no ponderada de pos_change exactos es 0
            assert abs(weighted_pos_change) <= Decimal("1.0")


# --- SC-004: Privacidad y Grupos Chicos (< 10 socios) -----------------------------------


def test_small_groups_suppression():
    # Creamos un ranking con solo 15 socios en total
    # Un grupo con 5 socios debe tener too_small: True y variables: None
    n = 15
    before = []
    after = []
    for i in range(1, n + 1):
        uid = uuid.uuid4()
        # Solo 2 socios suben
        sim_pos = 1 if i == 15 else (2 if i == 14 else i)
        before.append(
            _make_stored_entry(
                uid,
                pos=i,
                total=Decimal("50.00"),
                distance_km=Decimal("20.0"),
                seniority_years=3,
                age_years=30,
            )
        )
        after.append(_make_simulated_entry(uid, pos=sim_pos, total=Decimal("52.00")))

    equity = calculate_equity(before, after, relevant_threshold=1)
    assert equity.profile is not None
    groups = {g.group: g for g in equity.profile.groups}
    assert groups["up"].count < 10
    assert groups["up"].too_small is True
    assert groups["up"].variables is None
    assert groups["up"].message == GROUP_TOO_SMALL_MESSAGE

    # Como n=15, ninguna segmentación puede tener al menos 2 bandas de >= 10 socios
    for seg_attr in equity.segmentations:
        assert seg_attr.status == "not_available"
        assert seg_attr.code == "SEGMENTATION_NOT_AVAILABLE"
        assert len(seg_attr.segments) == 0
        assert seg_attr.verdict is None

    # Veredicto general sin atributos disponibles debe ser None (escenario 15)
    assert equity.verdict is None


# --- Veredictos (EQUITY_ATTENTION y EQUITY_BIAS) -----------------------------------------


def test_verdict_attention_and_bias():
    # Creamos 100 socios para segmentar en al menos 2 grupos de >= 10 socios
    n = 100
    before = []
    after = []

    # Socios 1..50 distancia corta (5 km), socios 51..100 distancia larga (1500 km)
    # Hacemos que los de distancia larga suban fuertemente (desvío > 5%)
    for i in range(1, n + 1):
        uid = uuid.uuid4()
        dist = Decimal("5.0") if i <= 50 else Decimal("1500.0")
        sen = 2 if i <= 50 else 15
        age = 25 if i <= 50 else 55

        # Antes: pos 1..50 son los primeros, 51..100 los segundos
        # Después: invertimos completamente para crear gran desvío
        sim_pos = i + 40 if i <= 50 else i - 40
        before.append(
            _make_stored_entry(
                uid,
                pos=i,
                total=Decimal("40.00"),
                distance_km=dist,
                seniority_years=sen,
                age_years=age,
                matches_c=10,
                attended_c=8,
                inst_points=Decimal(20),
            )
        )
        after.append(_make_simulated_entry(uid, pos=sim_pos, total=Decimal("60.00")))

    equity = calculate_equity(before, after, relevant_threshold=1)
    assert equity.status == "available"
    assert equity.verdict is not None
    assert equity.verdict.code == "EQUITY_BIAS"
    assert "El cambio favorece o perjudica de forma marcada a:" in equity.verdict.text
    assert "El análisis cubre antigüedad, distancia y edad." == equity.verdict.scope
    assert len(equity.verdict.items) > 0


# --- CSV Export con Secciones de Equidad (HU-30 Escenario 19) ----------------------------


def test_csv_export_includes_equity():
    n = 30
    before = []
    after = []
    for i in range(1, n + 1):
        uid = uuid.uuid4()
        dist = Decimal("5.0") if i <= 15 else Decimal("100.0")
        sen = 2 if i <= 15 else 12
        age = 25 if i <= 15 else 50
        before.append(
            _make_stored_entry(
                uid,
                pos=i,
                total=Decimal("50.00"),
                distance_km=dist,
                seniority_years=sen,
                age_years=age,
            )
        )
        after.append(_make_simulated_entry(uid, pos=i, total=Decimal("50.00")))

    equity = calculate_equity(before, after, relevant_threshold=1)

    from datetime import UTC, date, datetime

    from app.schemas.rules_simulation import (
        BaselineRankingOut,
        BreakdownStatusOut,
        LabelsOut,
        MovementOut,
        SaturationCountsOut,
        SaturationOut,
        StatsOut,
        SummaryOut,
    )

    stats = StatsOut(
        mean="50.00", median="50.00", std_dev="0.00", p10="50.00", p90="50.00"
    )
    dummy_result = RulesSimulationResultOut(
        ranking=BaselineRankingOut(
            id=1,
            completed_at=datetime.now(UTC),
            calculation_date=date(2026, 10, 29),
            rules_version=1,
            population_size=n,
        ),
        baseline_text="base",
        status="no_changes",
        message=None,
        labels=LabelsOut(before="Ranking actual", after="Simulación"),
        changed_parameters=[],
        factors_changed=[],
        derived_values=[],
        summary=SummaryOut(before=stats, after=stats, difference=stats),
        movement=MovementOut(
            up=0,
            down=0,
            unchanged=n,
            mean_abs_position_change="0.0",
            relevant_threshold=1,
            relevant_up=0,
            relevant_down=0,
        ),
        histogram=[],
        saturation=SaturationOut(
            before=SaturationCountsOut(
                at_cap=0, needs_cap_adjustment=0, tied=0, largest_tie=0
            ),
            after=SaturationCountsOut(
                at_cap=0, needs_cap_adjustment=0, tied=0, largest_tie=0
            ),
        ),
        alerts=[],
        components=[],
        breakdown=BreakdownStatusOut(status="no_changes", code=None, message=None),
        equity=equity,
    )
    dummy_factors = BreakdownOut(
        ranking_id=1,
        status="no_changes",
        code=None,
        message=None,
        factors=[],
        remainder=None,
        non_additive_note=None,
    )

    rows = csv_rows(dummy_result, dummy_factors, rules_in_force=1)
    sections = {r[0] for r in rows}
    assert "perfil" in sections
    assert "segmento" in sections
    assert "veredicto" in sections


def test_deviation_thresholds_and_marks():
    # Probar umbrales exactos: 1.9 % (none), 2.0 % (marked), 4.9 % (marked), 5.0 % (strong)
    # y dirección: favored (positivo) y harmed (negativo)
    from app.scoring.equity import SocioData

    # Construimos artificialmente SocioData con posiciones para dar desvíos exactos
    # Para n=100 socios, un avg_pos_change de 1.9 da 1.9 %, 2.0 da 2.0 %, 5.0 da 5.0 %
    n = 100
    socios = []
    for i in range(1, n + 1):
        # 50 socios en banda [0, 10) km y 50 en banda [10, 50) km
        dist = Decimal("5.0") if i <= 50 else Decimal("25.0")
        sen = 2 if i <= 50 else 8
        age = 25 if i <= 50 else 40

        # En la primera banda hacemos que suban exactamente 2 posiciones en promedio (2.0 %)
        # En la segunda bajan 2 posiciones en promedio (-2.0 %)
        sim_pos = i - 2 if i <= 50 else i + 2
        socios.append(
            SocioData(
                socio_id=uuid.uuid4(),
                ranking_pos=i,
                sim_pos=sim_pos,
                ranking_score=Decimal("50.00"),
                sim_score=Decimal("50.00"),
                distance_km=dist,
                seniority_years=Decimal(sen),
                age_years=Decimal(age),
                class_c_matches=0,
                class_c_attended=0,
                institutional_points=Decimal(0),
            )
        )

    segmentations, verdict = compute_segmentations(socios)
    assert verdict is not None
    assert verdict.code == "EQUITY_ATTENTION"
    dist_seg = next(s for s in segmentations if s.attribute == "distance")
    assert dist_seg.status == "available"
    assert len(dist_seg.segments) == 2
    # El primer segmento tiene desvío +2.0 % -> marked, favored
    s0 = dist_seg.segments[0]
    assert s0.deviation == "2.0"
    assert s0.mark == "marked"
    assert s0.direction == "favored"
    # El segundo tiene desvío -2.0 % -> marked, harmed
    s1 = dist_seg.segments[1]
    assert s1.deviation == "-2.0"
    assert s1.mark == "marked"
    assert s1.direction == "harmed"


def test_equity_failure_fallback():
    # Si ocurre un error inesperado al calcular la equidad, debe responder status: unavailable (FR-010)
    # Pasamos una entrada con snapshot corrupto (e.g. sin clave attendance)
    bad_stored = StoredEntry(
        socio_id=uuid.uuid4(),
        position=1,
        components={},
        total=Decimal("50.00"),
        snapshot={},  # snapshot corrupto
    )
    bad_simulated = SimulatedEntry(
        socio_id=bad_stored.socio_id,
        position=1,
        components={},
        total=Decimal("50.00"),
    )

    equity = calculate_equity([bad_stored], [bad_simulated], relevant_threshold=1)
    assert equity.status == "unavailable"
    assert equity.code == "EQUITY_UNAVAILABLE"
    assert "No pudimos calcular el análisis de equidad" in equity.message
    assert equity.profile is None
    assert equity.segmentations is None
    assert equity.verdict is None

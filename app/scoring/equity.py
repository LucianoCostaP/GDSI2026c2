"""Análisis de equidad de una simulación de reglas (HU-30).

Código puro y determinístico, sin base de datos ni reloj.
Calcula sobre la instantánea guardada en el ranking (`StoredEntry.snapshot`)
y las posiciones simuladas (`SimulatedEntry.position`):
1. Perfil de los socios que se mueven (Suben, Bajan, Sin cambio relevante, Todos) con las 5
   variables y la protección de grupos chicos (< 10 socios).
2. Equidad por segmentos (antigüedad, distancia y edad) con bandas fijas y la regla
   determinística de fusión.
3. Desvío de cada segmento, marcas ('none', 'marked' >= 2 %, 'strong' >= 5 %), etiqueta 'Mayor desvío'
   y veredictos (por atributo y general).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from ..schemas.rules_simulation import (
    AttributeVerdictOut,
    BandOut,
    EquityOut,
    MoverClassCOut,
    MoverGroupOut,
    MoverProfileOut,
    MoverVariableOut,
    MoverVariablesOut,
    OverallVerdictOut,
    SegmentationOut,
    SegmentOut,
    VerdictItemOut,
)
from .distribution import median
from .formatting import decimal_fixed, format_decimal
from .rules_simulation import SimulatedEntry, StoredEntry

MIN_GROUP_SIZE = 10
MIN_SEGMENT_SIZE = 10

GROUP_TOO_SMALL_MESSAGE = "Grupo demasiado chico para mostrar su perfil."
SEGMENTATION_NOT_AVAILABLE_MESSAGE = (
    "No hay suficientes socios para comparar grupos por {atributo}."
)
EQUITY_UNAVAILABLE_MESSAGE = (
    "No pudimos calcular el análisis de equidad. Los resultados generales siguen "
    "siendo válidos."
)

EQUITY_OK_TEXT = "Sin diferencias marcadas: el cambio no favorece ni perjudica de más a ningún grupo."
EQUITY_ATTENTION_PREFIX = "Hay grupos con diferencias para revisar: "
EQUITY_BIAS_PREFIX = "El cambio favorece o perjudica de forma marcada a: "
SCOPE_NOTICE = "El análisis cubre antigüedad, distancia y edad."

ATTRIBUTE_LABELS = {
    "seniority": "antigüedad",
    "distance": "distancia",
    "age": "edad",
}

INITIAL_BANDS: dict[str, list[tuple[int, int | None]]] = {
    "seniority": [(0, 1), (1, 5), (5, 10), (10, 20), (20, None)],
    "distance": [
        (0, 10),
        (10, 50),
        (50, 200),
        (200, 500),
        (500, 1000),
        (1000, 2000),
        (2000, None),
    ],
    "age": [(0, 30), (30, 45), (45, 60), (60, 75), (75, None)],
}


def band_label(attribute: str, lower: int, upper: int | None) -> str:
    """Genera la etiqueta en español de una banda (inicial o fusionada)."""
    if attribute == "distance":
        if lower == 0 and upper is not None:
            return f"menos de {upper} km"
        if upper is not None:
            return f"de {lower} a menos de {upper} km"
        return f"{lower} km o más"

    if attribute == "seniority":
        if lower == 0 and upper == 1:
            return "menos de 1 año"
        if lower == 0 and upper is not None:
            return f"menos de {upper} años"
        if lower == 1 and upper is not None:
            return f"de 1 a menos de {upper} años"
        if upper is not None:
            return f"de {lower} a menos de {upper} años"
        if lower == 1:
            return "1 año o más"
        return f"{lower} años o más"

    if attribute == "age":
        if lower == 0 and upper is not None:
            return f"menos de {upper} años"
        if upper is not None:
            return f"de {lower} a menos de {upper} años"
        return f"{lower} años o más"

    return f"[{lower}, {upper})"


@dataclass(frozen=True)
class SocioData:
    """Datos necesarios de un socio para el análisis de equidad."""

    socio_id: Any
    ranking_pos: int
    sim_pos: int
    ranking_score: Decimal
    sim_score: Decimal
    distance_km: Decimal
    seniority_years: Decimal
    age_years: Decimal
    class_c_matches: int
    class_c_attended: int
    institutional_points: Decimal

    @property
    def pos_change(self) -> int:
        """Cambio de posición = ranking - simulación (positivo = sube)."""
        return self.ranking_pos - self.sim_pos

    @property
    def has_class_c(self) -> bool:
        return self.class_c_matches > 0

    @property
    def class_c_percentage(self) -> Decimal:
        if self.class_c_matches == 0:
            return Decimal(0)
        return Decimal(100 * self.class_c_attended) / Decimal(self.class_c_matches)

    @property
    def has_institutional_points(self) -> bool:
        return self.institutional_points > 0


def _extract_socio_data(
    before: Sequence[StoredEntry], after: Sequence[SimulatedEntry]
) -> list[SocioData]:
    """Extrae las variables del snapshot y une posiciones de antes y después."""
    after_map = {entry.socio_id: entry for entry in after}
    data: list[SocioData] = []
    for entry in before:
        sim = after_map[entry.socio_id]
        snap = entry.snapshot
        att = snap["attendance"]
        mem = snap["membership"]
        inst = snap["institutional"]

        matches_c = int(att.get("matches_by_class", {}).get("C", 0))
        attended_c = int(att.get("attended_by_class", {}).get("C", 0))

        data.append(
            SocioData(
                socio_id=entry.socio_id,
                ranking_pos=entry.position,
                sim_pos=sim.position,
                ranking_score=entry.total,
                sim_score=sim.total,
                distance_km=Decimal(str(att["distance_km"])),
                seniority_years=Decimal(str(mem["seniority_years"])),
                age_years=Decimal(str(mem["age_years"])),
                class_c_matches=matches_c,
                class_c_attended=attended_c,
                institutional_points=Decimal(str(inst["points"])),
            )
        )
    return data


# --- 1. Perfil de los socios que se mueven (Mover Profile) --------------------------------


@dataclass(frozen=True)
class GroupMedians:
    distance_km: Decimal
    seniority_years: Decimal
    age_years: Decimal
    class_c_count: int
    class_c_pct: Decimal | None
    institutional_points: Decimal
    with_institutional_pct: Decimal


def _calculate_medians(members: Sequence[SocioData]) -> GroupMedians:
    dist = median(sorted(s.distance_km for s in members))
    sen = median(sorted(s.seniority_years for s in members))
    age = median(sorted(s.age_years for s in members))
    inst_pts = median(sorted(s.institutional_points for s in members))
    with_inst = Decimal(
        100 * sum(1 for s in members if s.has_institutional_points)
    ) / Decimal(len(members))

    eligible_c = [s.class_c_percentage for s in members if s.has_class_c]
    c_count = len(eligible_c)
    c_pct = median(sorted(eligible_c)) if c_count >= MIN_GROUP_SIZE else None

    return GroupMedians(
        distance_km=dist,
        seniority_years=sen,
        age_years=age,
        class_c_count=c_count,
        class_c_pct=c_pct,
        institutional_points=inst_pts,
        with_institutional_pct=with_inst,
    )


def compute_mover_profile(
    socios: Sequence[SocioData], relevant_threshold: int
) -> MoverProfileOut:
    n = len(socios)
    if n == 0:
        return MoverProfileOut(relevant_threshold=relevant_threshold, groups=[])

    all_medians = _calculate_medians(socios)

    up_members = [s for s in socios if s.pos_change >= relevant_threshold]
    down_members = [s for s in socios if s.pos_change <= -relevant_threshold]
    no_change_members = [
        s for s in socios if -relevant_threshold < s.pos_change < relevant_threshold
    ]

    groups_data = [
        ("up", "Suben", up_members),
        ("down", "Bajan", down_members),
        ("no_change", "Sin cambio relevante", no_change_members),
        ("all", "Todos", list(socios)),
    ]

    groups_out: list[MoverGroupOut] = []
    for key, label, members in groups_data:
        count = len(members)
        share = decimal_fixed(Decimal(100 * count) / Decimal(n), 1)

        if count < MIN_GROUP_SIZE:
            groups_out.append(
                MoverGroupOut(
                    group=key,  # type: ignore[arg-type]
                    label=label,
                    count=count,
                    share=share,
                    too_small=True,
                    message=GROUP_TOO_SMALL_MESSAGE,
                    variables=None,
                )
            )
            continue

        g_med = _calculate_medians(members)

        if key == "all":
            # En 'all', value == all y difference == "0.0" (contrato §5.3)
            dist_var = MoverVariableOut(
                value=decimal_fixed(g_med.distance_km, 1),
                all=decimal_fixed(all_medians.distance_km, 1),
                difference="0.0",
            )
            sen_var = MoverVariableOut(
                value=decimal_fixed(g_med.seniority_years, 1),
                all=decimal_fixed(all_medians.seniority_years, 1),
                difference="0.0",
            )
            age_var = MoverVariableOut(
                value=decimal_fixed(g_med.age_years, 1),
                all=decimal_fixed(all_medians.age_years, 1),
                difference="0.0",
            )
            inst_var = MoverVariableOut(
                value=decimal_fixed(g_med.institutional_points, 1),
                all=decimal_fixed(all_medians.institutional_points, 1),
                difference="0.0",
            )
            with_inst_var = MoverVariableOut(
                value=decimal_fixed(g_med.with_institutional_pct, 1),
                all=decimal_fixed(all_medians.with_institutional_pct, 1),
                difference="0.0",
            )
            if g_med.class_c_pct is None:
                class_c_var = MoverClassCOut(
                    value=None,
                    all=None,
                    difference=None,
                    count=g_med.class_c_count,
                    too_small=True,
                    message=GROUP_TOO_SMALL_MESSAGE,
                )
            else:
                class_c_var = MoverClassCOut(
                    value=decimal_fixed(g_med.class_c_pct, 1),
                    all=decimal_fixed(all_medians.class_c_pct, 1),  # type: ignore[arg-type]
                    difference="0.0",
                    count=g_med.class_c_count,
                    too_small=False,
                    message=None,
                )
        else:
            dist_var = MoverVariableOut(
                value=decimal_fixed(g_med.distance_km, 1),
                all=decimal_fixed(all_medians.distance_km, 1),
                difference=decimal_fixed(
                    g_med.distance_km - all_medians.distance_km, 1
                ),
            )
            sen_var = MoverVariableOut(
                value=decimal_fixed(g_med.seniority_years, 1),
                all=decimal_fixed(all_medians.seniority_years, 1),
                difference=decimal_fixed(
                    g_med.seniority_years - all_medians.seniority_years, 1
                ),
            )
            age_var = MoverVariableOut(
                value=decimal_fixed(g_med.age_years, 1),
                all=decimal_fixed(all_medians.age_years, 1),
                difference=decimal_fixed(g_med.age_years - all_medians.age_years, 1),
            )
            inst_var = MoverVariableOut(
                value=decimal_fixed(g_med.institutional_points, 1),
                all=decimal_fixed(all_medians.institutional_points, 1),
                difference=decimal_fixed(
                    g_med.institutional_points - all_medians.institutional_points, 1
                ),
            )
            with_inst_var = MoverVariableOut(
                value=decimal_fixed(g_med.with_institutional_pct, 1),
                all=decimal_fixed(all_medians.with_institutional_pct, 1),
                difference=decimal_fixed(
                    g_med.with_institutional_pct - all_medians.with_institutional_pct, 1
                ),
            )

            if g_med.class_c_pct is None or all_medians.class_c_pct is None:
                class_c_var = MoverClassCOut(
                    value=None,
                    all=None,
                    difference=None,
                    count=g_med.class_c_count,
                    too_small=True,
                    message=GROUP_TOO_SMALL_MESSAGE,
                )
            else:
                class_c_var = MoverClassCOut(
                    value=decimal_fixed(g_med.class_c_pct, 1),
                    all=decimal_fixed(all_medians.class_c_pct, 1),
                    difference=decimal_fixed(
                        g_med.class_c_pct - all_medians.class_c_pct, 1
                    ),
                    count=g_med.class_c_count,
                    too_small=False,
                    message=None,
                )

        groups_out.append(
            MoverGroupOut(
                group=key,  # type: ignore[arg-type]
                label=label,
                count=count,
                share=share,
                too_small=False,
                message=None,
                variables=MoverVariablesOut(
                    distance_km=dist_var,
                    seniority_years=sen_var,
                    age_years=age_var,
                    class_c_attendance=class_c_var,
                    institutional_points=inst_var,
                    with_institutional=with_inst_var,
                ),
            )
        )

    return MoverProfileOut(relevant_threshold=relevant_threshold, groups=groups_out)


# --- 2. Bandas y Regla Determinística de Fusión -------------------------------------------


@dataclass
class _BandRecord:
    lower: int
    upper: int | None
    members: list[SocioData]


def merge_bands(records: list[_BandRecord]) -> list[_BandRecord]:
    """Regla de fusión determinística (spec 'Bands').

    Mientras haya alguna banda con menos de 10 socios y quede más de una banda:
    - Se busca la banda con menos socios (empate: la más baja).
    - Se fusiona con la vecina que tenga menos socios (empate: la vecina más baja).
    """
    bands = list(records)
    while any(len(b.members) < MIN_SEGMENT_SIZE for b in bands) and len(bands) > 1:
        min_idx = 0
        min_count = len(bands[0].members)
        for idx in range(1, len(bands)):
            c = len(bands[idx].members)
            if c < min_count:
                min_count = c
                min_idx = idx

        if min_idx == 0:
            merge_with = 1
        elif min_idx == len(bands) - 1:
            merge_with = len(bands) - 2
        else:
            left_count = len(bands[min_idx - 1].members)
            right_count = len(bands[min_idx + 1].members)
            if left_count < right_count:
                merge_with = min_idx - 1
            elif right_count < left_count:
                merge_with = min_idx + 1
            else:
                merge_with = min_idx - 1

        first_idx = min(min_idx, merge_with)
        second_idx = max(min_idx, merge_with)

        b1 = bands[first_idx]
        b2 = bands[second_idx]

        merged = _BandRecord(
            lower=b1.lower,
            upper=b2.upper,
            members=b1.members + b2.members,
        )
        bands = bands[:first_idx] + [merged] + bands[second_idx + 1 :]

    return bands


# --- 3. Segmentación y Veredictos --------------------------------------------------------


@dataclass(frozen=True)
class _CalculatedSegment:
    band_out: BandOut
    count: int
    avg_score_before: Decimal
    avg_score_after: Decimal
    avg_score_difference: Decimal
    avg_pos_before: Decimal
    avg_pos_after: Decimal
    avg_pos_change: Decimal
    deviation_exact: Decimal
    mark: Literal["none", "marked", "strong"]
    direction: Literal["favored", "harmed"] | None


def _format_item_text(
    attr_label: str,
    band_label_str: str,
    direction: str,
    deviation_exact: Decimal,
) -> str:
    dir_str = "favorecido" if direction == "favored" else "perjudicado"
    abs_dev = abs(deviation_exact)
    dev_str = format_decimal(Decimal(decimal_fixed(abs_dev, 1)))
    return f"{attr_label}: {band_label_str} ({dir_str}, {dev_str} % del ranking)"


def compute_segmentations(
    socios: Sequence[SocioData],
) -> tuple[list[SegmentationOut], OverallVerdictOut | None]:
    n = len(socios)
    attributes: list[Literal["seniority", "distance", "age"]] = [
        "seniority",
        "distance",
        "age",
    ]

    segmentations_out: list[SegmentationOut] = []
    all_marked_items: list[tuple[Decimal, VerdictItemOut, str]] = []
    any_attribute_available = False
    has_strong_overall = False
    has_marked_overall = False

    for attr in attributes:
        attr_label = ATTRIBUTE_LABELS[attr]
        initial_defs = INITIAL_BANDS[attr]

        def get_attr_value(s: SocioData, target_attr: str = attr) -> Decimal:
            if target_attr == "seniority":
                return s.seniority_years
            if target_attr == "distance":
                return s.distance_km
            return s.age_years

        records: list[_BandRecord] = []
        for low, up in initial_defs:
            if up is None:
                members = [s for s in socios if get_attr_value(s) >= low]
            else:
                members = [s for s in socios if low <= get_attr_value(s) < up]
            records.append(_BandRecord(lower=low, upper=up, members=members))

        merged = merge_bands(records)

        # Si no puede retener al menos 2 segmentos de 10 o más socios:
        if len(merged) < 2 or any(len(b.members) < MIN_SEGMENT_SIZE for b in merged):
            segmentations_out.append(
                SegmentationOut(
                    attribute=attr,
                    label=attr_label,
                    status="not_available",
                    code="SEGMENTATION_NOT_AVAILABLE",
                    message=SEGMENTATION_NOT_AVAILABLE_MESSAGE.format(
                        atributo=attr_label
                    ),
                    segments=[],
                    verdict=None,
                )
            )
            continue

        any_attribute_available = True
        calc_segments: list[_CalculatedSegment] = []

        for b in merged:
            count = len(b.members)
            b_label = band_label(attr, b.lower, b.upper)
            band_out = BandOut(
                lower=str(b.lower),
                upper=str(b.upper) if b.upper is not None else None,
                label=b_label,
            )

            score_before = sum(s.ranking_score for s in b.members) / Decimal(count)
            score_after = sum(s.sim_score for s in b.members) / Decimal(count)
            score_diff = score_after - score_before

            pos_before = sum(Decimal(s.ranking_pos) for s in b.members) / Decimal(count)
            pos_after = sum(Decimal(s.sim_pos) for s in b.members) / Decimal(count)
            pos_change = sum(Decimal(s.pos_change) for s in b.members) / Decimal(count)

            dev_exact = (
                (Decimal(100) * pos_change / Decimal(n)) if n > 0 else Decimal(0)
            )

            abs_dev = abs(dev_exact)
            if abs_dev >= Decimal(5):
                mark: Literal["none", "marked", "strong"] = "strong"
                direction: Literal["favored", "harmed"] | None = (
                    "favored" if dev_exact > 0 else "harmed"
                )
            elif abs_dev >= Decimal(2):
                mark = "marked"
                direction = "favored" if dev_exact > 0 else "harmed"
            else:
                mark = "none"
                direction = None

            calc_segments.append(
                _CalculatedSegment(
                    band_out=band_out,
                    count=count,
                    avg_score_before=score_before,
                    avg_score_after=score_after,
                    avg_score_difference=score_diff,
                    avg_pos_before=pos_before,
                    avg_pos_after=pos_after,
                    avg_pos_change=pos_change,
                    deviation_exact=dev_exact,
                    mark=mark,
                    direction=direction,
                )
            )

        # Identificar mayor desvío (siempre que != 0; empate: banda más baja)
        max_abs_dev = max(abs(cs.deviation_exact) for cs in calc_segments)
        largest_found = False
        final_segments: list[SegmentOut] = []

        for cs in calc_segments:
            is_largest = False
            if (
                max_abs_dev > 0
                and not largest_found
                and abs(cs.deviation_exact) == max_abs_dev
            ):
                is_largest = True
                largest_found = True

            final_segments.append(
                SegmentOut(
                    band=cs.band_out,
                    count=cs.count,
                    avg_score_before=decimal_fixed(cs.avg_score_before, 2),
                    avg_score_after=decimal_fixed(cs.avg_score_after, 2),
                    avg_score_difference=decimal_fixed(cs.avg_score_difference, 2),
                    avg_position_before=decimal_fixed(cs.avg_pos_before, 1),
                    avg_position_after=decimal_fixed(cs.avg_pos_after, 1),
                    avg_position_change=decimal_fixed(cs.avg_pos_change, 1),
                    deviation=decimal_fixed(cs.deviation_exact, 1),
                    mark=cs.mark,
                    direction=cs.direction,
                    largest_deviation=is_largest,
                )
            )

        # Veredicto del atributo
        marked_for_attr = [cs for cs in calc_segments if cs.mark != "none"]
        # Ordenar por |desvío| decreciente (contrato §5.3)
        marked_for_attr.sort(key=lambda cs: abs(cs.deviation_exact), reverse=True)

        if not marked_for_attr:
            attr_verdict = AttributeVerdictOut(
                code="EQUITY_OK",
                text=EQUITY_OK_TEXT,
            )
        else:
            is_strong = any(cs.mark == "strong" for cs in marked_for_attr)
            items_str_list = [
                _format_item_text(
                    attr_label,
                    cs.band_out.label,
                    cs.direction,  # type: ignore[arg-type]
                    cs.deviation_exact,
                )
                for cs in marked_for_attr
            ]
            items_str = "; ".join(items_str_list)

            if is_strong:
                has_strong_overall = True
                attr_verdict = AttributeVerdictOut(
                    code="EQUITY_BIAS",
                    text=f"{EQUITY_BIAS_PREFIX}{items_str}.",
                )
            else:
                has_marked_overall = True
                attr_verdict = AttributeVerdictOut(
                    code="EQUITY_ATTENTION",
                    text=f"{EQUITY_ATTENTION_PREFIX}{items_str}.",
                )

        segmentations_out.append(
            SegmentationOut(
                attribute=attr,
                label=attr_label,
                status="available",
                code=None,
                message=None,
                segments=final_segments,
                verdict=attr_verdict,
            )
        )

        for cs in marked_for_attr:
            item_out = VerdictItemOut(
                attribute=attr,
                band=cs.band_out.label,
                direction=cs.direction,  # type: ignore[arg-type]
                deviation=decimal_fixed(cs.deviation_exact, 1),
                mark=cs.mark,  # type: ignore[arg-type]
            )
            item_str = _format_item_text(
                attr_label,
                cs.band_out.label,
                cs.direction,  # type: ignore[arg-type]
                cs.deviation_exact,
            )
            all_marked_items.append((abs(cs.deviation_exact), item_out, item_str))

    # Veredicto general
    if not any_attribute_available:
        overall_verdict = None
    else:
        # Ordenar todos los items marcados por |desvío| decreciente
        all_marked_items.sort(key=lambda x: x[0], reverse=True)
        items_out = [x[1] for x in all_marked_items]

        if has_strong_overall:
            code: Literal["EQUITY_OK", "EQUITY_ATTENTION", "EQUITY_BIAS"] = (
                "EQUITY_BIAS"
            )
            text_str = (
                f"{EQUITY_BIAS_PREFIX}{'; '.join(x[2] for x in all_marked_items)}."
            )
        elif has_marked_overall:
            code = "EQUITY_ATTENTION"
            text_str = (
                f"{EQUITY_ATTENTION_PREFIX}{'; '.join(x[2] for x in all_marked_items)}."
            )
        else:
            code = "EQUITY_OK"
            text_str = EQUITY_OK_TEXT

        overall_verdict = OverallVerdictOut(
            code=code,
            text=text_str,
            scope=SCOPE_NOTICE,
            items=items_out,
        )

    return segmentations_out, overall_verdict


# --- 4. Entrada Principal de Cálculo -----------------------------------------------------


def calculate_equity(
    before: Sequence[StoredEntry],
    after: Sequence[SimulatedEntry],
    relevant_threshold: int,
) -> EquityOut:
    """Calcula el análisis de equidad completo de HU-30."""
    try:
        socios = _extract_socio_data(before, after)
        profile = compute_mover_profile(socios, relevant_threshold)
        segmentations, overall_verdict = compute_segmentations(socios)
        return EquityOut(
            status="available",
            code=None,
            message=None,
            profile=profile,
            segmentations=segmentations,
            verdict=overall_verdict,
        )
    except Exception:  # noqa: BLE001
        return EquityOut(
            status="unavailable",
            code="EQUITY_UNAVAILABLE",
            message=EQUITY_UNAVAILABLE_MESSAGE,
            profile=None,
            segmentations=None,
            verdict=None,
        )

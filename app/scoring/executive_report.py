"""Cálculo puro y determinístico del Reporte Ejecutivo de Scoring y Equidad (HU-42)."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..schemas.executive_report import (
    ExecutiveAttributeEquityOut,
    ExecutiveDemographicEquityOut,
    ExecutiveReportSummary,
    ExecutiveSegmentOut,
    HistogramBinOut,
    PercentilesOut,
    PillarsAverageOut,
    TiesOut,
)
from .distribution import BINS, histogram, percentile, summary
from .equity import (
    ATTRIBUTE_LABELS,
    INITIAL_BANDS,
    MIN_SEGMENT_SIZE,
    SEGMENTATION_NOT_AVAILABLE_MESSAGE,
    band_label,
    merge_bands,
)
from .formatting import decimal_fixed


@dataclass(frozen=True)
class ExecutiveSocioData:
    """Datos agregados de un socio extraídos del ranking vigente para el reporte."""

    socio_id: Any
    position: int
    total: Decimal
    attendance: Decimal
    institutional: Decimal
    seniority_age: Decimal
    new_member_bonus: Decimal
    distance_km: Decimal
    seniority_years: Decimal
    age_years: Decimal


@dataclass
class _BandRecord:
    lower: int
    upper: int | None
    members: list[ExecutiveSocioData]


def extract_executive_socios(entries: Sequence[Any]) -> list[ExecutiveSocioData]:
    """Extrae los datos numéricos y demográficos necesarios de las entradas del ranking."""
    data: list[ExecutiveSocioData] = []
    for e in entries:
        inputs = e.inputs or {}
        att = inputs.get("attendance", {})
        mem = inputs.get("membership", {})

        dist = Decimal(str(att.get("distance_km", 0)))
        sen = Decimal(str(mem.get("seniority_years", 0)))
        age = Decimal(str(mem.get("age_years", 0)))

        # P_asistencia total = attendance_frequency + attendance_distance
        att_score = Decimal(str(e.attendance_frequency)) + Decimal(
            str(e.attendance_distance)
        )

        data.append(
            ExecutiveSocioData(
                socio_id=e.socio_id,
                position=int(e.position),
                total=Decimal(str(e.total)),
                attendance=att_score,
                institutional=Decimal(str(e.institutional)),
                seniority_age=Decimal(str(e.seniority_age)),
                new_member_bonus=Decimal(str(e.new_member_bonus)),
                distance_km=dist,
                seniority_years=sen,
                age_years=age,
            )
        )
    return data


def compute_executive_summary(
    socios: Sequence[ExecutiveSocioData],
) -> ExecutiveReportSummary:
    """Calcula las métricas estadísticas globales de tendencia central y dispersión."""
    totals = [s.total for s in socios]
    n = len(totals)
    ordered = sorted(totals)
    stats = summary(totals)

    # Conteo de empates
    counts = Counter(totals)
    tied_count = sum(c for c in counts.values() if c > 1)
    largest_tie = max(counts.values()) if tied_count > 0 else 0
    at_cap_count = sum(1 for t in totals if t == Decimal(100))

    return ExecutiveReportSummary(
        total_socios=n,
        mean_score=decimal_fixed(stats.mean, 2),
        median_score=decimal_fixed(stats.median, 1),
        std_dev=decimal_fixed(stats.std_dev, 2),
        percentiles=PercentilesOut(
            p10=decimal_fixed(percentile(ordered, 10), 1),
            p25=decimal_fixed(percentile(ordered, 25), 1),
            p75=decimal_fixed(percentile(ordered, 75), 1),
            p90=decimal_fixed(percentile(ordered, 90), 1),
        ),
        socios_at_cap=at_cap_count,
        ties=TiesOut(
            tied_socios_count=tied_count,
            largest_tie_size=largest_tie,
        ),
    )


def compute_executive_histogram(
    socios: Sequence[ExecutiveSocioData],
) -> list[HistogramBinOut]:
    """Genera el histograma de 20 bins [0-100] de ancho 5."""
    totals = [s.total for s in socios]
    n = len(totals)
    counts = histogram(totals)
    result: list[HistogramBinOut] = []

    for bin_obj, count in zip(BINS, counts, strict=True):
        share = decimal_fixed(Decimal(count * 100) / n, 1) if n > 0 else "0.0"
        result.append(
            HistogramBinOut(
                lower=bin_obj.lower,
                upper=bin_obj.upper,
                label=bin_obj.label,
                count=count,
                share_percent=share,
            )
        )
    return result


def compute_pillars_average(socios: Sequence[ExecutiveSocioData]) -> PillarsAverageOut:
    """Calcula los promedios globales de cada pilar evaluado en el ranking."""
    n = Decimal(len(socios))
    avg_att = sum((s.attendance for s in socios), Decimal(0)) / n
    avg_inst = sum((s.institutional for s in socios), Decimal(0)) / n
    avg_sen = sum((s.seniority_age for s in socios), Decimal(0)) / n
    avg_bonus = sum((s.new_member_bonus for s in socios), Decimal(0)) / n

    return PillarsAverageOut(
        asistencia=decimal_fixed(avg_att, 2),
        institucional=decimal_fixed(avg_inst, 2),
        antiguedad=decimal_fixed(avg_sen, 2),
        bonus_nuevo=decimal_fixed(avg_bonus, 2),
    )


def compute_executive_demographics(
    socios: Sequence[ExecutiveSocioData],
) -> ExecutiveDemographicEquityOut:
    """Calcula la equidad demográfica por tramos de antigüedad, distancia y edad."""
    n = len(socios)

    def _segment_attribute(attr: str) -> ExecutiveAttributeEquityOut:
        attr_label = ATTRIBUTE_LABELS[attr]
        initial_defs = INITIAL_BANDS[attr]

        def get_val(s: ExecutiveSocioData) -> Decimal:
            if attr == "seniority":
                return s.seniority_years
            if attr == "distance":
                return s.distance_km
            return s.age_years

        records: list[Any] = []
        for low, up in initial_defs:
            if up is None:
                members = [s for s in socios if get_val(s) >= low]
            else:
                members = [s for s in socios if low <= get_val(s) < up]
            records.append(_BandRecord(lower=low, upper=up, members=members))

        merged = merge_bands(records)

        # Si no puede retener al menos 2 segmentos de 10 o más socios:
        if len(merged) < 2 or any(len(b.members) < MIN_SEGMENT_SIZE for b in merged):
            return ExecutiveAttributeEquityOut(
                available=False,
                code="SEGMENTATION_NOT_AVAILABLE",
                message=SEGMENTATION_NOT_AVAILABLE_MESSAGE.format(atributo=attr_label),
                segments=[],
            )

        segments: list[ExecutiveSegmentOut] = []
        for b in merged:
            band_members: list[ExecutiveSocioData] = b.members  # type: ignore[assignment]
            count = len(band_members)
            share = decimal_fixed(Decimal(count * 100) / n, 1)
            avg_score = sum((m.total for m in band_members), Decimal(0)) / count
            avg_pos = Decimal(sum(m.position for m in band_members)) / count

            segments.append(
                ExecutiveSegmentOut(
                    band_label=band_label(attr, b.lower, b.upper),
                    socio_count=count,
                    share_percent=share,
                    average_score=decimal_fixed(avg_score, 2),
                    average_position=decimal_fixed(avg_pos, 1),
                )
            )

        return ExecutiveAttributeEquityOut(
            available=True,
            code=None,
            message=None,
            segments=segments,
        )

    return ExecutiveDemographicEquityOut(
        seniority=_segment_attribute("seniority"),
        distance=_segment_attribute("distance"),
        age=_segment_attribute("age"),
    )

"""Generación y exportación de archivo CSV para el Reporte Ejecutivo de Scoring (HU-42)."""

import csv
import io
from datetime import datetime

from ..core.date_utils import a_hora_buenos_aires
from ..schemas.executive_report import ExecutiveScoringReportOut

HEADER = ("seccion", "categoria", "metrica", "valor", "unidad_o_detalle")
Row = tuple[str, str, str, str, str]


def executive_report_filename(now: datetime) -> str:
    """Nombre de archivo estandarizado con timestamp en Buenos Aires."""
    return f"reporte-ejecutivo-scoring-{a_hora_buenos_aires(now):%Y%m%d-%H%M}.csv"


def executive_report_csv_bytes(report: ExecutiveScoringReportOut) -> bytes:
    """Genera el contenido del CSV en bytes con codificación UTF-8 BOM."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(HEADER)
    writer.writerows(_build_rows(report))
    return buffer.getvalue().encode("utf-8-sig")


def _build_rows(report: ExecutiveScoringReportOut) -> list[Row]:
    rows: list[Row] = []

    # 1. Metadatos
    meta = report.metadata
    rows.append(("1. Metadatos", "General", "Club", meta.club_name, str(meta.club_id)))
    rows.append(
        (
            "1. Metadatos",
            "General",
            "Generado el",
            f"{a_hora_buenos_aires(meta.generated_at):%Y-%m-%d %H:%M:%S}",
            "Hora Buenos Aires",
        )
    )
    rows.append(
        ("1. Metadatos", "General", "Generado por", meta.generated_by, "Administrador")
    )
    rows.append(
        ("1. Metadatos", "Ranking", "ID Ranking Base", str(meta.ranking_id), "")
    )
    rows.append(
        (
            "1. Metadatos",
            "Ranking",
            "Fecha Cálculo Ranking",
            f"{a_hora_buenos_aires(meta.ranking_calculated_at):%Y-%m-%d %H:%M:%S}",
            "Timestamp",
        )
    )
    rows.append(
        (
            "1. Metadatos",
            "Reglas",
            "Versión de Reglas",
            f"{meta.rules_version.formula_id} v{meta.rules_version.version}",
            "Catálogo",
        )
    )

    for param, val in meta.rules_version.parameters.items():
        rows.append(("1. Metadatos", "Parámetros", param, str(val), "Valor Vigente"))

    # 2. Resumen Global
    summ = report.summary
    rows.append(
        (
            "2. Resumen Global",
            "Población",
            "Total Socios Evaluados",
            str(summ.total_socios),
            "socios",
        )
    )
    rows.append(
        (
            "2. Resumen Global",
            "Tendencia Central",
            "Media de Puntaje",
            str(summ.mean_score),
            "puntos",
        )
    )
    rows.append(
        (
            "2. Resumen Global",
            "Tendencia Central",
            "Mediana de Puntaje",
            str(summ.median_score),
            "puntos",
        )
    )
    rows.append(
        (
            "2. Resumen Global",
            "Dispersión",
            "Desvío Estándar",
            str(summ.std_dev),
            "puntos",
        )
    )
    rows.append(
        (
            "2. Resumen Global",
            "Percentiles",
            "Percentil 10 (P10)",
            str(summ.percentiles.p10),
            "puntos",
        )
    )
    rows.append(
        (
            "2. Resumen Global",
            "Percentiles",
            "Percentil 25 (P25)",
            str(summ.percentiles.p25),
            "puntos",
        )
    )
    rows.append(
        (
            "2. Resumen Global",
            "Percentiles",
            "Percentil 75 (P75)",
            str(summ.percentiles.p75),
            "puntos",
        )
    )
    rows.append(
        (
            "2. Resumen Global",
            "Percentiles",
            "Percentil 90 (P90)",
            str(summ.percentiles.p90),
            "puntos",
        )
    )
    rows.append(
        (
            "2. Resumen Global",
            "Extremos",
            "Socios en el Tope (100 pts)",
            str(summ.socios_at_cap),
            "socios",
        )
    )
    rows.append(
        (
            "2. Resumen Global",
            "Empates",
            "Socios Empatados",
            str(summ.ties.tied_socios_count),
            "socios",
        )
    )
    rows.append(
        (
            "2. Resumen Global",
            "Empates",
            "Empate más Grande",
            str(summ.ties.largest_tie_size),
            "socios en mismo puntaje",
        )
    )

    # 3. Promedio por Pilar
    pil = report.pillars_average
    rows.append(
        (
            "3. Pilares de Scoring",
            "Promedios",
            "Asistencia (Frecuencia + Distancia)",
            str(pil.asistencia),
            "puntos promedio",
        )
    )
    rows.append(
        (
            "3. Pilares de Scoring",
            "Promedios",
            "Participación Institucional",
            str(pil.institucional),
            "puntos promedio",
        )
    )
    rows.append(
        (
            "3. Pilares de Scoring",
            "Promedios",
            "Antigüedad",
            str(pil.antiguedad),
            "puntos promedio",
        )
    )
    rows.append(
        (
            "3. Pilares de Scoring",
            "Promedios",
            "Bonus Nuevo Socio",
            str(pil.bonus_nuevo),
            "puntos promedio",
        )
    )

    # 4. Histograma
    for b in report.histogram:
        rows.append(
            (
                "4. Histograma",
                "Distribución de Puntajes",
                b.label,
                str(b.count),
                f"{b.share_percent} %",
            )
        )

    # 5. Equidad Demográfica
    eq = report.demographic_equity
    for attr_name, attr_label, eq_data in [
        ("seniority", "Antigüedad", eq.seniority),
        ("distance", "Distancia", eq.distance),
        ("age", "Edad", eq.age),
    ]:
        if not eq_data.available:
            rows.append(
                (
                    "5. Equidad Demográfica",
                    attr_label,
                    "Estado",
                    "No disponible",
                    eq_data.message or "",
                )
            )
            continue

        for seg in eq_data.segments:
            rows.append(
                (
                    "5. Equidad Demográfica",
                    attr_label,
                    seg.band_label,
                    f"{seg.socio_count} socios ({seg.share_percent} %)",
                    f"Puntaje Prom: {seg.average_score} | Posición Prom: {seg.average_position}",
                )
            )

    return rows

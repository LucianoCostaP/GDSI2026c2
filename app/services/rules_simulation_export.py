"""CSV de la simulación de cambio de reglas (HU-29, escenario 26; formato en "Export").

UTF-8 con BOM, una fila de encabezado, punto decimal y coma como separador. Columnas `seccion`,
`elemento`, `antes`, `despues`, `diferencia`: una fila por cifra de la pantalla, en el orden de
la pantalla, con las celdas vacías donde no aplica. Solo agregados: nunca datos de un socio.

Las cifras son las mismas de las respuestas JSON (mismos redondeos). Donde hay antes y después
numéricos y la pantalla no trae una diferencia (histograma, saturación, parámetros), la
diferencia es después − antes, exacta. Las secciones de HU-30 (`perfil`, `segmento`,
`veredicto`) se agregan cuando exista el análisis de equidad.
"""

import csv
import io
from datetime import datetime
from decimal import Decimal

from ..core.date_utils import a_hora_buenos_aires
from ..schemas.rules_simulation import BreakdownOut, RulesSimulationResultOut
from ..scoring.formatting import decimal_to_str

HEADER = ("seccion", "elemento", "antes", "despues", "diferencia")
Row = tuple[str, str, str, str, str]

SUMMARY_LABELS = {
    "mean": "media",
    "median": "mediana",
    "std_dev": "desvío estándar",
    "p10": "percentil 10",
    "p90": "percentil 90",
}
SATURATION_LABELS = {
    "at_cap": "en el tope de 100",
    "needs_cap_adjustment": "con ajuste por tope",
    "tied": "empatados",
    "largest_tie": "empate más grande",
}


def filename(now: datetime) -> str:
    """`simulacion-reglas-AAAAMMDD-HHMM.csv`, con la hora de Buenos Aires de la descarga."""
    return f"simulacion-reglas-{a_hora_buenos_aires(now):%Y%m%d-%H%M}.csv"


def csv_bytes(rows: list[Row]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def csv_rows(
    result: RulesSimulationResultOut, factors: BreakdownOut, rules_in_force: int
) -> list[Row]:
    """Las filas, sección por sección. `parametro_aislado` solo si el desglose estuvo
    disponible: con `single_factor`, `no_changes` o `unavailable` no se mostró."""
    return [
        *_context(result, rules_in_force),
        *_parameters(result),
        *_summary(result),
        *_histogram(result),
        *_saturation(result),
        *_components(result),
        *(_isolated(factors) if factors.status == "available" else []),
    ]


def _row(
    section: str, element: str, before: str = "", after: str = "", difference: str = ""
) -> Row:
    return (section, element, before, after, difference)


def _difference(before: str, after: str) -> str:
    return decimal_to_str(Decimal(after) - Decimal(before))


def _context(result: RulesSimulationResultOut, rules_in_force: int) -> list[Row]:
    moment = a_hora_buenos_aires(result.ranking.completed_at)
    return [
        _row("contexto", "ranking calculado", f"{moment:%d/%m/%Y %H:%M}"),
        _row(
            "contexto",
            "versión de reglas del ranking",
            str(result.ranking.rules_version),
        ),
        _row("contexto", "versión de reglas vigente", str(rules_in_force)),
    ]


def _parameters(result: RulesSimulationResultOut) -> list[Row]:
    return [
        _row(
            "parametros",
            p.symbol,
            p.before,
            p.after,
            _difference(p.before, p.after),
        )
        for p in result.changed_parameters
    ]


def _summary(result: RulesSimulationResultOut) -> list[Row]:
    s, moved = result.summary, result.movement
    stats = [
        _row(
            "resumen",
            label,
            getattr(s.before, key),
            getattr(s.after, key),
            getattr(s.difference, key),
        )
        for key, label in SUMMARY_LABELS.items()
    ]
    counts = [
        ("suben", moved.up),
        ("bajan", moved.down),
        ("sin cambios", moved.unchanged),
        (f"suben {moved.relevant_threshold} posiciones o más", moved.relevant_up),
        (f"bajan {moved.relevant_threshold} posiciones o más", moved.relevant_down),
    ]
    return [
        *stats,
        *(_row("resumen", label, after=str(count)) for label, count in counts),
        _row(
            "resumen",
            "cambio absoluto medio de posición",
            after=moved.mean_abs_position_change,
        ),
    ]


def _histogram(result: RulesSimulationResultOut) -> list[Row]:
    # `;` en vez de `,` dentro del rango, para que se lea igual sin comillas.
    return [
        _row(
            "histograma",
            b.label.replace(",", ";"),
            str(b.before),
            str(b.after),
            str(b.after - b.before),
        )
        for b in result.histogram
    ]


def _saturation(result: RulesSimulationResultOut) -> list[Row]:
    before, after = result.saturation.before, result.saturation.after
    return [
        _row(
            "saturacion",
            label,
            str(getattr(before, key)),
            str(getattr(after, key)),
            str(getattr(after, key) - getattr(before, key)),
        )
        for key, label in SATURATION_LABELS.items()
    ]


def _components(result: RulesSimulationResultOut) -> list[Row]:
    return [
        _row("componentes", c.label, c.before, c.after, c.difference)
        for c in result.components
    ]


def _isolated(factors: BreakdownOut) -> list[Row]:
    rows = []
    for f in factors.factors:
        rows += [
            _row(
                "parametro_aislado",
                f"{f.label}: cambio del total medio",
                difference=f.mean_total_change,
            ),
            _row("parametro_aislado", f"{f.label}: suben", after=str(f.up)),
            _row("parametro_aislado", f"{f.label}: bajan", after=str(f.down)),
            _row(
                "parametro_aislado",
                f"{f.label}: cambio absoluto medio de posición",
                after=f.mean_abs_position_change,
            ),
        ]
    if factors.remainder:
        rows.append(
            _row(
                "parametro_aislado",
                factors.remainder.label,
                difference=factors.remainder.mean_total_change,
            )
        )
    return rows

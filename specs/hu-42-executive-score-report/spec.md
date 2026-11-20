# Feature Specification: Executive Scoring & Equity Report

**Feature Branch**: `feat/hu-42-executive-score-report`
**Created**: 2026-11-15
**Status**: Draft (v1)
**Backlog Reference**: HU-42 (Estimate: 3, Priority: Baja, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md), [HU-25 ranking calculation](../hu-25-ranking-calculation/spec.md), [HU-30 equity analysis](../hu-30-equity-analysis/spec.md)
**Input**: "Como Administrador, quiero generar un reporte ejecutivo sobre las métricas actuales del sistema de scoring, para responder ante los socios de forma clara y transparente."

---

## Business Questions Answered

This report provides the club's Board of Directors (Comisión Directiva) and Management with an official, consolidated, and auditable summary of the current scoring distribution and demographic equity. It is purely descriptive of the in-force ranking (unlike HU-29/HU-30, it performs no hypothetical simulations and does not alter rules or scores).

| # | Business question | What is shown | Decision it supports |
|---|---|---|---|
| 1 | **What is the current distribution of scores across the membership?** | Population size, mean, median, standard deviation, percentiles (P10, P25, P75, P90), and a 20-bin histogram [0–100]. | Evaluating if the current rules produce healthy score dispersion or undesired concentration. |
| 2 | **Are the active rules treating demographic groups equitably?** | Equity breakdown across Seniority (`T`), Distance to stadium (`di`), and Age (`E`), displaying each segment's average score and average ranking position. | Answering member inquiries, justifying criteria before the Board, and detecting historical imbalances. |
| 3 | **Which rules and data snapshot produced these figures?** | Full audit header: rules version number, formula parameters (`wA`, `wP`, `wT`, `αA`, `dsat`, `Pinst_max`), baseline ranking calculation timestamp, and issuing admin. | Ensuring traceability, regulatory compliance, and non-repudiation. |

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Generate Executive Scoring Report (Priority: P2)

As an Admin of the club, I want to request a consolidated executive report of the current scoring and ranking metrics, so that I can explain and defend the current state of the membership before the Board of Directors and the Socios with official data.

**Why this priority**: Empowers management with authoritative, auditable metrics without requiring technical database queries or ad-hoc spreadsheets.

**Independent Test**: Log in as an Admin, access the Executive Report endpoint/view, and verify that the response returns the exact mean, median, histogram, and demographic segments computed from the active ranking, matching the rules version in force, with complete audit metadata and zero mutations to the database.

---

### Acceptance Scenarios

#### 1. Scope and Baseline Data Source
1. **Given** an Admin authenticated, **When** they request the executive scoring report, **Then** the report is generated exclusively from the latest completed and in-force ranking of the club (`Ranking` and its `RankingEntry` rows with their `inputs_snapshot`).
2. **Given** the report generation, **When** it executes, **Then** it reads only the in-force ranking and its formula parameters; it does NOT trigger any re-calculation, does NOT run any simulation, and does NOT modify any score, position, ranking, or rule.
3. **Given** no completed ranking exists for the club, **When** the report is requested, **Then** the request is rejected with `404 Not Found` and message `NO_BASELINE` ("Todavía no hay un ranking calculado. Calculá el ranking para generar el reporte ejecutivo.").
4. **Given** the latest ranking has 0 Socios, **When** the report is requested, **Then** the request is rejected with `422 Unprocessable Entity` and message `EMPTY_RANKING` ("El ranking vigente no tiene socios: no hay datos para generar el reporte.").
5. **Given** a user with the role of Socio, **When** they attempt to access the executive report, **Then** the request is rejected with `403 Forbidden` (`FORBIDDEN`).

#### 2. Global Distribution and Central Tendency
6. **Given** the active ranking population `N`, **When** the global metrics are computed, **Then** the report includes:
   * **Total evaluated Socios** (`total_socios` = `N`).
   * **Mean score** (`mean_score`): arithmetic mean of total scores, rounded to 2 decimal places.
   * **Median score** (`median_score`): median total score, rounded to 1 decimal place.
   * **Score percentiles**: P10, P25, P75, P90 rounded to 1 decimal place.
   * **Histogram**: 20 fixed bins of width 5 (`[0,5)`, `[5,10)`, ..., `[95,100]`), each showing its lower bound, upper bound, socio count, and percentage of total population.
7. **Given** the score totals, **When** examining extremes and ties, **Then** the report includes:
   * **Top-score count** (`socios_at_cap`): number of Socios reaching exactly 100 points.
   * **Ties summary**: total count of Socios sharing their score with at least one other Socio, and size of the largest tie block.

#### 3. Component Averages (Pillars)
8. **Given** the breakdown of scores, **When** the component summary is generated, **Then** the report displays the overall average score for each pillar across all `N` Socios:
   * `mean_asistencia`: Average of `P_asistencia` contribution.
   * `mean_institucional`: Average of `P_inst` contribution.
   * `mean_antiguedad`: Average of `P_antigüedad` contribution.
   * `mean_bonus_nuevo`: Average of `B_nuevo` contribution.

#### 4. Equity and Demographic Segmentation (HU-30 Alignment)
9. **Given** the Socios in the ranking, **When** the equity analysis is computed, **Then** Socios are segmented across the three standard demographic attributes defined in HU-30:
   * **Seniority (`T`)**: `[0,1)`, `[1,5)`, `[5,10)`, `[10,20)`, `[20,∞)` years.
   * **Distance (`di`)**: `[0,10)`, `[10,50)`, `[50,200)`, `[200,500)`, `[500,1000)`, `[1000,2000)`, `[2000,∞)` km.
   * **Age (`E`)**: `[0,30)`, `[30,45)`, `[45,60)`, `[60,75)`, `[75,∞)` years.
10. **Given** each demographic segment, **When** presented in the report, **Then** it displays:
    * `band_label`: human-readable range description in Spanish (e.g., "de 1 a menos de 5 años").
    * `socio_count`: absolute count of Socios in this segment.
    * `share_percent`: percentage of the total club ranking represented by this segment (`socio_count / N * 100`).
    * `average_score`: mean total score of Socios in this segment (2 decimals).
    * `average_position`: mean ranking position of Socios in this segment (1 decimal).
11. **Given** a demographic segment with fewer than 10 Socios, **When** generating the report, **Then** it is merged with its adjacent neighbor following the deterministic merge rule of HU-30 to protect privacy and avoid statistical noise. If after merging an attribute cannot retain at least two valid segments of ≥ 10 Socios, the attribute shows `SEGMENTATION_NOT_AVAILABLE`.

#### 5. Audit Header and Traceability Metadata
12. **Given** the generated report, **When** returned, **Then** it contains a comprehensive audit metadata object (`metadata`):
    * `generated_at`: ISO 8601 timestamp in timezone `America/Argentina/Buenos_Aires`.
    * `generated_by_admin`: email or identifier of the Admin requesting the report.
    * `club_id` and `club_name`: tenant identification.
    * `ranking_id`: UUID of the baseline ranking.
    * `ranking_calculated_at`: timestamp of when the baseline ranking was finalized.
    * `rules_version`: formula identifier (e.g., `scoring-model`) and version number.
    * `parameters_in_force`: dictionary of active parameter values (`wA`, `wP`, `wT`, `alpha_a`, `d_sat`, `Pinst_max`, `B_nuevo`).

#### 6. Export Capability (Tabular CSV & JSON)
13. **Given** the executive report, **When** the Admin requests the CSV format (`GET /api/v1/admin/reports/executive-scoring/csv` or `Accept: text/csv`), **Then** a downloadable CSV file is streamed with UTF-8 BOM encoding, containing:
    * Section 1: Audit Metadata (Club, Rules Version, Calculation Date, Generated At).
    * Section 2: Global Statistics (Total Socios, Mean, Median, P10, P90, Max Score Count).
    * Section 3: Histogram Distribution (Bin, Range, Count, Percentage).
    * Section 4: Pillar Averages.
    * Section 5: Demographic Equity Tables (Seniority, Distance, Age with Count, %, Avg Score, Avg Position).
14. **Given** any format, **When** the report is generated, **Then** it NEVER exposes PII (no individual DNI, name, member ID, or address); only aggregated metrics are returned.

---

### Edge Cases

* **Single-member or tiny club**: If `N < 10`, segmentation by bands triggers `SEGMENTATION_NOT_AVAILABLE`, but global metrics (mean, median, histogram, pillars) remain fully available.
* **Ties in median**: If `N` is even, median is the arithmetic mean of the two middle scores.
* **Ranking updated while viewing**: The report is a stateless point-in-time snapshot of the latest ranking at the moment the endpoint is queried.
* **Multi-tenant isolation**: The Admin only receives data from their own club (`club_id`).

---

## Bands & Calculation Definitions *(mandatory)*

Reuses the exact bands and deterministic rules from [HU-30 Equity Analysis](../hu-30-equity-analysis/spec.md):

| Attribute | Initial Bands | Unit |
|---|---|---|
| Seniority `T` | `[0,1)`, `[1,5)`, `[5,10)`, `[10,20)`, `[20,∞)` | Years |
| Distance `di` | `[0,10)`, `[10,50)`, `[50,200)`, `[200,500)`, `[500,1000)`, `[1000,2000)`, `[2000,∞)` | Kilometers |
| Age `E` | `[0,30)`, `[30,45)`, `[45,60)`, `[60,75)`, `[75,∞)` | Years |

* **Deterministic Merge Rule**: While any band has `< 10` Socios, merge the smallest band (ties: lower) with its smallest adjacent neighbor. Merged label is the union of ranges.
* **Histogram**: 20 bins `[0,5), [5,10), ..., [90,95), [95,100]` with `bin_index(total) = min(int(total // 5), 19)`.
* **Averages**: Score averages shown with 2 decimals, position averages with 1 decimal.

---

## Messages and Error Codes *(mandatory)*

Texts in Spanish (`es-AR`), produced by the server:

| Situation | HTTP Status | Code | Message |
|---|---|---|---|
| No ranking calculated | `404 Not Found` | `NO_BASELINE` | Todavía no hay un ranking calculado. Calculá el ranking para poder generar el reporte ejecutivo. |
| Ranking has 0 members | `422 Unprocessable` | `EMPTY_RANKING` | El ranking vigente no tiene socios: no hay datos para generar el reporte. |
| Socio tries to access | `403 Forbidden` | `FORBIDDEN` | No tenés permisos para acceder al reporte ejecutivo de scoring. |
| Attribute cannot be segmented | Included in JSON | `SEGMENTATION_NOT_AVAILABLE` | No hay suficientes socios para segmentar por {atributo}. |

---

## Requirements *(mandatory)*

### Functional Requirements

* **FR-001**: System MUST provide endpoint `GET /admin/reports/executive-scoring` accessible only to authenticated users with role `Admin`.
* **FR-002**: System MUST generate metrics solely from the club's in-force completed ranking snapshot, without executing simulations or writing to the database.
* **FR-003**: System MUST compute global distribution metrics: total population `N`, arithmetic mean, median, percentiles (10, 25, 75, 90), and 20-bin histogram.
* **FR-004**: System MUST compute pillar averages (`P_asistencia`, `P_inst`, `P_antigüedad`, `B_nuevo`).
* **FR-005**: System MUST segment Socios by Seniority, Distance, and Age into fixed bands, reporting count, share %, average score, and average position per segment.
* **FR-006**: System MUST enforce the 10-Socio privacy threshold per segment using deterministic merging.
* **FR-007**: System MUST provide full audit metadata in the report header (timestamp, rules version, parameters, ranking ID, issuer).
* **FR-008**: System MUST support CSV tabular download via `GET /admin/reports/executive-scoring/csv`.
* **FR-009**: System MUST NOT expose any individual socio PII in the report response or CSV export.
* **FR-010**: System MUST enforce multi-tenancy by scoping results strictly to the Admin's `club_id`.

---

## Key Entities & API Contract

### Endpoints

1. `GET /admin/reports/executive-scoring` -> Returns `ExecutiveScoringReportOut` (JSON).
2. `GET /admin/reports/executive-scoring/csv` -> Streams downloadable file `reporte_ejecutivo_scoring_<fecha>.csv`.

### Response Schema (`ExecutiveScoringReportOut`)

```json
{
  "metadata": {
    "generated_at": "2026-11-15T20:30:00-03:00",
    "generated_by": "admin@club.com",
    "club_id": "11111111-1111-1111-1111-111111111111",
    "club_name": "Club Atlético Ejemplo",
    "ranking_id": "22222222-2222-2222-2222-222222222222",
    "ranking_calculated_at": "2026-11-04T18:00:00-03:00",
    "rules_version": {
      "formula_id": "scoring-model",
      "version": 1,
      "parameters": {
        "wA": "0.60",
        "wP": "0.20",
        "wT": "0.20",
        "alpha_a": "0.30",
        "d_sat": "400.0",
        "p_inst_max": "30.0",
        "b_nuevo": "0.0"
      }
    }
  },
  "summary": {
    "total_socios": 144,
    "mean_score": "58.42",
    "median_score": "59.1",
    "percentiles": {
      "p10": "28.4",
      "p25": "44.2",
      "p75": "73.8",
      "p90": "86.5"
    },
    "socios_at_cap": 2,
    "ties": {
      "tied_socios_count": 18,
      "largest_tie_size": 3
    }
  },
  "histogram": [
    { "lower": 0, "upper": 5, "label": "[0,5)", "count": 3, "share_percent": "2.1" },
    { "lower": 5, "upper": 10, "label": "[5,10)", "count": 5, "share_percent": "3.5" },
    "... (20 bins total) ...",
    { "lower": 95, "upper": 100, "label": "[95,100]", "count": 2, "share_percent": "1.4" }
  ],
  "pillars_average": {
    "asistencia": "34.15",
    "institucional": "12.30",
    "antiguedad": "11.97",
    "bonus_nuevo": "0.00"
  },
  "demographic_equity": {
    "seniority": {
      "available": true,
      "segments": [
        { "band_label": "menos de 1 año", "socio_count": 22, "share_percent": "15.3", "average_score": "38.20", "average_position": "112.4" },
        { "band_label": "de 1 a menos de 5 años", "socio_count": 45, "share_percent": "31.2", "average_score": "52.10", "average_position": "78.2" },
        { "band_label": "de 5 a menos de 10 años", "socio_count": 38, "share_percent": "26.4", "average_score": "64.50", "average_position": "55.1" },
        { "band_label": "de 10 a menos de 20 años", "socio_count": 25, "share_percent": "17.4", "average_score": "74.80", "average_position": "32.0" },
        { "band_label": "20 años o más", "socio_count": 14, "share_percent": "9.7", "average_score": "86.30", "average_position": "15.6" }
      ]
    },
    "distance": {
      "available": true,
      "segments": [
        { "band_label": "menos de 10 km", "socio_count": 65, "share_percent": "45.1", "average_score": "62.40", "average_position": "66.3" },
        { "band_label": "de 10 a menos de 50 km", "socio_count": 48, "share_percent": "33.3", "average_score": "56.20", "average_position": "74.8" },
        { "band_label": "50 km o más", "socio_count": 31, "share_percent": "21.6", "average_score": "53.50", "average_position": "79.1" }
      ]
    },
    "age": {
      "available": true,
      "segments": [
        { "band_label": "menos de 30 años", "socio_count": 34, "share_percent": "23.6", "average_score": "48.90", "average_position": "88.5" },
        { "band_label": "de 30 a menos de 45 años", "socio_count": 52, "share_percent": "36.1", "average_score": "59.40", "average_position": "69.2" },
        { "band_label": "de 45 a menos de 60 años", "socio_count": 36, "share_percent": "25.0", "average_score": "64.10", "average_position": "58.4" },
        { "band_label": "60 años o más", "socio_count": 22, "share_percent": "15.3", "average_score": "66.70", "average_position": "52.0" }
      ]
    }
  }
}
```

---

## Success Criteria *(mandatory)*

* **SC-001**: 100% of reported metrics match the exact arithmetic calculations of `distribution.py` and `equity.py` computed over the active ranking.
* **SC-002**: For each demographic attribute, the sum of `socio_count` across all segments equals exactly `N`, and `share_percent` sums to 100.0%.
* **SC-003**: 0 database write operations or audit logs are produced upon calling the report endpoint.
* **SC-004**: 0 individual socio identifiers or PII fields appear in the report response.
* **SC-005**: Response time for generating the report is `< 500 ms` on rankings up to 100.000 socios (reusing pre-aggregated snapshots).

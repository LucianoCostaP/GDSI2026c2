# Feature Specification: Equity Analysis of a Rules Simulation

**Feature Branch**: `hu-30-equity-analysis`
**Created**: 2026-10-25 (v1) | **Revised**: 2026-11-07 (v2)
**Status**: Draft
**Backlog Reference**: HU-30 (Estimate: 5, Priority: Media, MVP: Yes). Re-estimate: besides the segments by band, it now includes the profile of the Socios who move up and down, a fixed deviation rule and a verdict.
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md), [HU-29 simulation](../hu-29-rules-change-impact-simulation/spec.md)
**Input**: "As an Admin, I want to see how a change of weights affects the different Socio profiles, so that I detect whether a new rule harms or benefits a group disproportionately before applying it."

## Business questions answered

HU-30 answers the first two questions of the result of a simulation; HU-29 answers the others and shows this analysis next to its results.

| # | Business question | What is shown | Decision it supports |
|---|---|---|---|
| 1 | Does the change reward what the club wants to reward? | Profile of the Socios who move up and of those who move down, against all Socios: distance, seniority, age, attendance at Clase C matches, institutional participation | Go ahead, correct the weight or discard the change |
| 2 | Whom does it harm or favor more than the rest? | Equity by seniority, distance and age, with the deviating segments marked and a verdict | Adjust to compensate, or defend the change before the Socios |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Equity Analysis of a Rules Simulation (Priority: P2)

As an Admin, I want to see how a change of parameters affects the different Socio profiles, so that I detect whether a new rule harms or benefits a group disproportionately before applying it.

**Why this priority**: The club must be able to defend its rules before its Socios; seeing which groups win or lose before applying a change is part of that.

**Independent Test**: Run a simulation (HU-29) that raises the distance weight and verify that, next to the general results: the Socios who move up are on average farther than all Socios; the distance segments show the expected changes in average score and position; the segments that exceed the thresholds are marked; the verdict names them; and that, with values equal to the ranking's, no segment is marked and the verdict is "sin diferencias marcadas".

**Acceptance Scenarios**:

*Place in the simulation*

1. **Given** a simulation of HU-29, **When** its result is shown, **Then** the equity analysis (profile of the movers and equity by segments, with the verdict) is shown next to it on the same screen, computed from the same hypothetical values and the same simulated positions; it is not a separate simulation and it needs no further request.
2. **Given** the analysis, **When** it runs, **Then** it reads only the inputs snapshot of the latest completed ranking and the simulated result of HU-29; it re-reads no other data, and no real score, position or rule changes.
3. **Given** no completed ranking, an empty ranking, a non-Admin user, an Admin without club, or invalid values, **When** a simulation is requested, **Then** the outcome is the one of HU-29 (`NO_BASELINE`, `EMPTY_RANKING`, `FORBIDDEN`, `ADMIN_WITHOUT_CLUB`, `INVALID_VALUES`) and no analysis is produced. The analysis uses the club and the ranking of the simulation (cross-cutting section 9).

*Profile of the Socios who move (question 1)*

4. **Given** a simulation, **When** the profile is shown, **Then** the Socios of the ranking are split in three groups by their change of position (definition in HU-29): **Suben** (up in a relevant way, change `≥ +m`), **Bajan** (down in a relevant way, `≤ −m`) and **Sin cambio relevante**; a fourth column **Todos** has the whole ranking. Each group shows its number of Socios and the share of the ranking.
5. **Given** the groups, **When** the profile is shown, **Then** for each group and for Todos it shows these five variables, taken from the snapshot: distance to the stadium in km (`distance_km`); seniority in years (`T`); age in years (`E`); attendance at Clase C matches, as the percentage of the Clase C matches counted for the Socio that the Socio attended (only Socios with at least one Clase C match counted take part, and their number is shown); institutional participation, as the raw points before the `Pinst_max` cap (inputs snapshot) and as the percentage of Socios with more than 0 points. For each variable except the percentage of Socios with participation, the figure is the **median**; for each group it is shown next to the median of Todos and the difference.
6. **Given** a group (or the Socios with Clase C matches inside a group) with fewer than 10 Socios, **When** the profile is shown, **Then** its number of Socios is shown but its values are not, with the message `GROUP_TOO_SMALL`, so no small group can be singled out.
7. **Given** a profile, **When** it is shown, **Then** it is descriptive: it is not marked or judged, because which profile the club wants to reward is the club's decision; the verdict of scenario 14 refers only to the equity by segments.

*Equity by segments (question 2)*

8. **Given** the analysis, **When** it is computed, **Then** the Socios are segmented by the three attributes at once: seniority (`T`, years of uninterrupted membership as stored in the snapshot, not years since the alta), distance to the stadium (km) and age (`E`, years), each in the fixed bands of "Bands". The Admin switches between the three attributes without a new simulation; the verdict of all three is always visible.
9. **Given** a segmentation, **When** it is shown, **Then** each segment shows its band, its number of Socios, its average score in the ranking and in the simulation and the difference (simulation minus ranking), its average position in the ranking and in the simulation and the average change of position (ranking minus simulation, positive meaning it goes up), and that change as a percentage of the ranking size `N` (the **deviation** of the segment).
10. **Given** a segment with fewer than 10 Socios, **When** the bands are built, **Then** it is merged with its neighbor band following the merge rule of "Bands", so no small group can be singled out. A merged segment shows the union of the ranges as its band.
11. **Given** the three segmentations, **When** one cannot keep at least two segments of 10 Socios or more after merging, **Then** that attribute shows `SEGMENTATION_NOT_AVAILABLE` and does not take part in the verdict.
12. **Given** the segments of an attribute, **When** they are shown, **Then** a segment is **marked** when the absolute value of its deviation is `2 %` or more (fixed in the product), as favored when positive and harmed when negative, and a segment whose deviation is `5 %` or more is marked as **strong**. The segment with the largest absolute deviation of the attribute carries the tag "mayor desvío" (ties: the lowest band) whenever that deviation is not 0, marked or not.
13. **Given** the thresholds, **When** no segment of any attribute reaches them, **Then** nothing is marked, only the tag "mayor desvío" remains, and a small change is never presented as bias.

*Verdict*

14. **Given** the available segmentations, **When** the verdict is shown, **Then** each attribute has a verdict and there is an overall one, the most severe of the three: `EQUITY_OK` when no segment is marked; `EQUITY_ATTENTION` when some are marked but none is strong; `EQUITY_BIAS` when some is strong. The text names the marked segments with their attribute, whether they are favored or harmed and their deviation, and states that the analysis covers seniority, distance and age only.
15. **Given** no attribute is available (scenario 11 for the three), **When** the verdict is requested, **Then** no verdict is given and the message `SEGMENTATION_NOT_AVAILABLE` is shown for each attribute.

*Consistency and failure*

16. **Given** hypothetical values identical to the rules of the ranking, **When** the analysis runs, **Then** every segment shows a difference of 0, no segment is marked, there is no "mayor desvío" tag, the verdict is `EQUITY_OK`, the groups "Suben" and "Bajan" are empty (`GROUP_TOO_SMALL`) and every Socio is in "Sin cambio relevante".
17. **Given** the segments of an attribute, **When** they are added up, **Then** their number of Socios adds up to `N`, the average score difference weighted by size equals the change of the mean total of HU-29, and the average change of position weighted by size is exactly 0.
18. **Given** the analysis cannot be computed, **When** the result of HU-29 is shown, **Then** the general results stay and the analysis section shows `EQUITY_UNAVAILABLE`.
19. **Given** the analysis shown, **When** the Admin downloads the result (HU-29, scenario 26), **Then** the CSV includes the profile, the segments and the verdict with the figures of the screen, aggregates only.
20. **Given** any analysis, **When** it is shown or returned, **Then** it contains aggregates only: no identifier, score or position of an individual Socio, and no list of Socios.

---

### Edge Cases

- **Same data as HU-29**: the analysis uses the inputs snapshot of the latest completed ranking (scoring model, rule 4), which stores `T`, `E`, the distance, the per-class counts of matches counted and attended and the raw participation points; it reads no other data. It reflects the ranking's calculation date (it does not age the Socios).
- **Segments do not depend on the hypothetical values**: the population and the snapshot are the same in every simulation of a ranking, so bands and merges are the same; only the figures change.
- **Zero-sum positions**: positions are a permutation, so the average change of position of all Socios is 0 and the deviation of a segment is already relative to the whole ranking. The average score changes for everyone (a change of weights can lower every score) and is shown for information; the marks and the verdict use the position, which is what the Socios experience.
- **Descriptive, not statistical**: the thresholds are fixed rules of the product, not a significance test. With a very small ranking the figures are noisy; the minimum of 10 Socios per segment limits the effect.
- **Thresholds are fixed values** (2 %, 5 %, 10 Socios, relevant movement of HU-29). They can only be changed by amending this spec.
- **Socio type**: the backlog suggests segmenting by "tipo de socio", but the data contract has no such field. It can be added when the club sends it (HU-43).
- **Per-class counts**: the profile needs the per-class counts in the snapshot, which HU-25 already stores (HU-18 relies on them too). The wording of scoring model rule 4 should name them (README, open items).
- **Other formulas**: written for the scoring model v1 (README, open items).
- **Performance**: it shares the time target of HU-29 for the main result (cross-cutting section 6).

## Bands *(mandatory)*

Bands are fixed in the product. Limits are lower-inclusive and upper-exclusive; the last band has no upper limit. Values are those of the snapshot (`T` and `E` are completed years, `distance_km` is in km).

| Attribute | Bands |
|---|---|
| Seniority `T` (years) | `[0,1)`, `[1,5)`, `[5,10)`, `[10,20)`, `[20,∞)` |
| Distance (km) | `[0,10)`, `[10,50)`, `[50,200)`, `[200,500)`, `[500,1000)`, `[1000,2000)`, `[2000,∞)` |
| Age `E` (years) | `[0,30)`, `[30,45)`, `[45,60)`, `[60,75)`, `[75,∞)` |

- The distance bands cover the whole range allowed for `dsat` (50–3000 km), so the zone where the curve acts is not one single band. The first age band includes any Socio under 18.
- **Merge rule** (deterministic): while a band has fewer than 10 Socios and more than one band remains, the band with the fewest Socios (ties: the lowest) is merged with the adjacent band that has fewer Socios (ties: the lower one); the first and last bands have only one neighbor. Empty bands are merged the same way. The merged band is labelled with the union of the ranges.
- Segments are built on the population of the ranking; merging is the same for the ranking and for the simulation.

## Calculation definitions *(mandatory)*

- **Change of position, relevant movement `m`, mean, median**: as defined in HU-29.
- **Deviation of a segment**: `100 × (mean change of position of its Socios) / N`, in percentage points of the ranking size, computed on exact values; marks and verdicts compare the exact value, the display is rounded to one decimal, half up.
- **Average score**: mean of the 2-decimal totals; shown with 2 decimals half up. **Average position**: shown with one decimal half up.
- **Attendance at Clase C matches** of a Socio: `100 × attended / counted`, over the Clase C matches counted for the Socio in the snapshot; Socios with 0 counted take no part in this variable.
- **Median of a group**: as in HU-29 (even count: mean of the two middle values), shown with one decimal half up.

## Messages and codes *(mandatory)*

Texts in Spanish (es-AR), produced by the server. Errors and codes common with HU-29 are listed there.

| Situation | Code | Message |
|---|---|---|
| Group too small for its profile | `GROUP_TOO_SMALL` | Grupo demasiado chico para mostrar su perfil. |
| Attribute that cannot be segmented | `SEGMENTATION_NOT_AVAILABLE` | No hay suficientes socios para comparar grupos por {atributo}. |
| Verdict, no marked segment | `EQUITY_OK` | Sin diferencias marcadas: el cambio no favorece ni perjudica de más a ningún grupo. |
| Verdict, marked segments | `EQUITY_ATTENTION` | Hay grupos con diferencias para revisar: {lista}. |
| Verdict, strong segment | `EQUITY_BIAS` | El cambio favorece o perjudica de forma marcada a: {lista}. |
| Item of {lista} | — | {atributo}: {banda} ({favorecido o perjudicado}, {x} % del ranking) |
| Scope of the verdict (shown with it) | — | El análisis cubre antigüedad, distancia y edad. |
| Tag of the largest deviation | — | Mayor desvío |
| Analysis not available | `EQUITY_UNAVAILABLE` | No pudimos calcular el análisis de equidad. Los resultados generales siguen siendo válidos. |
| Labels of the three groups | — | Suben / Bajan / Sin cambio relevante / Todos |

Labels of bands are generated from their limits: «menos de 1 año», «de 1 a menos de 5 años», «20 años o más»; for distance «km» in the same way; for a merged band, the union of the ranges.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST compute the analysis over the same simulation as HU-29, from the same snapshot and the same simulated positions, show it next to its general results, and not require any further request.
- **FR-002**: System MUST split the Socios in "Suben", "Bajan" and "Sin cambio relevante" with the relevant movement of HU-29, and show for each group and for all Socios the median distance, seniority, age and attendance at Clase C matches, the median of the raw institutional points and the share with points, with the difference against all Socios.
- **FR-003**: System MUST NOT show the values of a group with fewer than 10 Socios (or fewer than 10 with Clase C matches for that variable).
- **FR-004**: System MUST segment the Socios by seniority (`T`), distance and age in the fixed bands, always the three attributes together.
- **FR-005**: System MUST show per segment the count, the average score and average position before and after, the differences and the deviation.
- **FR-006**: System MUST merge segments with fewer than 10 Socios with the rule of "Bands", and mark the attribute as not available when it cannot keep two segments.
- **FR-007**: System MUST mark the segments whose deviation is 2 % or more in absolute value, mark as strong those with 5 % or more, and tag the largest deviation of each attribute when it is not 0.
- **FR-008**: System MUST give a verdict per attribute and an overall one (`EQUITY_OK`, `EQUITY_ATTENTION`, `EQUITY_BIAS`) with the rule of scenario 14, naming the marked segments and stating its scope.
- **FR-009**: System MUST NOT modify any real data, MUST return aggregates only, and MUST apply the permissions and club of HU-29.
- **FR-010**: System MUST keep the general results of HU-29 when the analysis fails (`EQUITY_UNAVAILABLE`).
- **FR-011**: System MUST give each user-facing message the exact text and code of "Messages and codes".

### Key Entities

- **EquitySegment**: attribute, band, number of Socios, average score and position before and after, average change of position, deviation, mark (none, marked, strong), tag. Transient, part of the RulesSimulation of HU-29.
- **MoverProfile**: group (Suben, Bajan, Sin cambio relevante, Todos), number of Socios, and the values of the five variables with their difference against all Socios. Transient, part of the RulesSimulation of HU-29.
- **EquityVerdict**: per attribute and overall level, with the list of marked segments. Transient.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With hypothetical values identical to the ranking's rules, every segment shows a difference of 0, no segment is marked and the verdict is `EQUITY_OK`.
- **SC-002**: For every attribute, the number of Socios of the segments adds up to `N`, their averages of score difference weighted by size equal the change of the mean total of HU-29, and the average change of position weighted by size is exactly 0.
- **SC-003**: In a hand-computed reference case, the marks, the "mayor desvío" tag and the verdict match the rule of scenarios 12 to 14, including values just below and just on each threshold, and the merge of bands matches the merge rule (including a first band, a last band, an empty band and a tie).
- **SC-004**: 0 results show the values of a group of fewer than 10 Socios, and 0 responses contain data of an individual Socio.
- **SC-005**: The groups "Suben", "Bajan" and "Sin cambio relevante" add up to `N`, and the counts of "Suben" and "Bajan" are consistent with the movement counts of HU-29.
- **SC-006**: The analysis is within the time target of HU-29 for the main result (it is included in it).

## Assumptions

- HU-42 (executive report, outside the MVP) reuses these segments and profiles.
- Decided: the profile uses medians (distances and tenures have long tails) and is not judged; only the equity by segments has a verdict.
- Decided: the marks and the verdict use the change of position relative to the size of the ranking, and the fixed thresholds of 2 % and 5 %, to be reviewed with the club once it has seen real simulations.
- Decided: bands are fixed in the product; the Admin does not edit them in the MVP.
- Decided: segmenting by "tipo de socio" stays out until the club sends that field.

## Revision Notes (v2)

- Added the profile of the Socios who move up and down (question 1), with the five variables and a minimum group size.
- Fixed the bands (limits, inclusivity, one band for any age below 30, distance bands covering the range of `dsat`), used the seniority `T` of the snapshot instead of "years since alta", and made the merge rule deterministic, with the case where an attribute cannot be segmented.
- Replaced "differ most from the rest" with a rule: deviation in percentage points of the ranking, marks at 2 % and 5 %, tag of the largest deviation, and a verdict per attribute and overall.
- Defined the sign of the changes, rounding, the weighted-sum check (SC-002 was trivial for positions), the three attributes computed together, the identity case, failure of the analysis, permissions and tenancy, and the CSV.
- Added the exact messages and codes.

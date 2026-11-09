# Feature Specification: Simulate Impact of a Rules Change

**Feature Branch**: `hu-29-rules-change-impact-simulation`
**Created**: 2026-10-11 | **Revised**: 2026-11-07 (v4)
**Status**: Draft
**Backlog Reference**: HU-29 (Estimate: 8, Priority: Media, MVP: Yes). Re-estimate: besides the distribution and the movement of the ranking, the result now answers four business questions (flatness and saturation, effect by component, effect by parameter) and includes the equity analysis of HU-30.
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md), [HU-30 equity analysis](../hu-30-equity-analysis/spec.md)
**Input**: "As an Admin, I want to simulate the impact of a change in weights before applying it, so that I can anticipate how the ranking would be redistributed without affecting the real scoring of Socios."

## Business questions answered

The result of a simulation answers these questions, each one tied to the decision it supports. HU-29 answers the third to fifth; HU-30 answers the first two and is shown on the same screen.

| # | Business question | What is shown | Decision it supports | Spec |
|---|---|---|---|---|
| 1 | Does the change reward what the club wants to reward? | Profile of the Socios who move up and down against the whole ranking: distance, seniority, age, attendance at Clase C matches, institutional participation | Go ahead, correct the weight or discard the change | HU-30 |
| 2 | Whom does it harm or favor more than the rest? | Equity by seniority, distance and age, deviating segments marked, with a verdict | Adjust to compensate, or defend the change before the Socios | HU-30 |
| 3 | How much of the change comes from each component and each parameter? | Mean change per score component; effect of each factor (pillar weights, distance weight, distance inflection) simulated on its own | Know which parameter explains the effect and which one to move | HU-29 |
| 4 | Did the ranking become too flat or saturated? | Dispersion of the scores, Socios at the cap of 100, ties | Avoid a change that "flattens" the differences | HU-29 |
| 5 | How is the ranking redistributed? | Histogram, mean, median, Socios moving up and down | Anticipate the redistribution before applying anything | HU-29 |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Simulate Impact of a Rules Change (Priority: P2)

As an Admin, I want to simulate the impact of a change in parameters before applying it, so that I can anticipate how the ranking would be redistributed without affecting the real scoring of Socios.

**Why this priority**: Lets decision makers preview the consequences of a rule change, and negotiate it knowing which parameter causes which effect.

**Independent Test**: As an Admin, with a completed ranking, change the distance weight and the pillar weights, run the simulation and verify: the side-by-side comparison with the ranking, the histogram, mean, median, dispersion, the Socios who move up and down, the saturation and tie counts, the change per component, the effect of each factor on its own, the equity analysis of HU-30 on the same screen, and that the real ranking, scores and rules are unchanged. Then run it again with the values of the ranking and verify that nothing changes.

**Acceptance Scenarios**:

*Access and baseline*

1. **Given** an Admin logged in and a completed ranking, **When** they open the simulator, **Then** every parameter of the formula (scoring model, section 4) is shown pre-filled with the values of the **rules version of that ranking**, with its limits and the derived values of the formula (for the scoring model v1, `b`) read-only; and a line states the baseline: "Comparado con el ranking calculado el {dd/mm/aaaa hh:mm} (reglas versión {n})." (text in "Messages").
2. **Given** the rules in force differ from the rules version of the ranking (for example, right after an adjustment in HU-28), **When** the simulator is opened, **Then** a notice states both versions and offers a control to load the rules in force into the form. Loading them only fills the form: it does not run the simulation and does not change anything real. Running it then shows how the ranking would look at its next calculation, with the data of the current ranking.
3. **Given** no completed ranking exists (none ever calculated, or only `running` or `failed` ones), **When** the Admin opens the simulator or requests a simulation, **Then** the message `NO_BASELINE` is shown and no form is offered. A ranking in `running` state does not change the baseline: it is still the latest `completed` one.
4. **Given** the latest completed ranking has no Socios, **When** a simulation is requested, **Then** it is rejected with `EMPTY_RANKING` and nothing is calculated.
5. **Given** a user who is not an Admin, **When** they try to open or run the simulator, **Then** they are rejected with `FORBIDDEN`; an Admin without club is rejected with `ADMIN_WITHOUT_CLUB`; an unauthenticated request with `NOT_AUTHENTICATED`. The club is taken from the account and the ranking read is the club's own (cross-cutting section 9); a club sent in the request is ignored.

*Validation*

6. **Given** hypothetical values, **When** any is missing, is not a number, is outside the limits of its parameter, is not a parameter of the formula, or the pillar weights do not add up to 1.00, **Then** the simulation is blocked with `INVALID_VALUES` and the list of violations, each with the code and text of HU-27 (`PARAMETER_MISSING`, `PARAMETER_NOT_A_NUMBER`, `PARAMETER_OUT_OF_LIMITS`, `PARAMETER_UNKNOWN`, `SUM_CONSTRAINT_VIOLATED`). All violations are returned together and nothing is calculated.
7. **Given** the formula is locked (HU-27), or the season cut-off of HU-28 has passed, **When** the Admin simulates, **Then** the simulation runs normally: those two rules govern **saving** official rules, not previewing them. The limits and the sum rule are those of the formula of the ranking's rules version.

*Calculation*

8. **Given** valid hypothetical values, **When** the simulation runs, **Then** every Socio of the latest completed ranking is recomputed from the stored inputs snapshot of its entry, with the calculation of the formula (the same one HU-25 uses) and the tiebreak of the scoring model (rule 5), obtaining components, total and position; no real data is modified and no source data is re-read. The population is exactly the Socios of that ranking.
9. **Given** hypothetical values identical to the rules version of the ranking, **When** it runs, **Then** every simulated component, total and position equals the stored one, 0 Socios go up and 0 go down, the distributions are equal, every change per component is 0, and the message `NO_CHANGES` is shown.
10. **Given** a new ranking completes while a simulation is running, or between two runs, **When** the result is shown, **Then** each result uses a single ranking, the one that was the latest completed at the moment the run started, and its date and rules version are shown (scenario 1); results of two rankings are never mixed.

*General results (question 5)*

11. **Given** a simulation result, **When** it is shown, **Then** it includes, for the ranking and for the simulation, a histogram of the totals in 20 fixed bins of 5 points (`[0,5)`, `[5,10)`, … `[90,95)`, and `[95,100]`, so a total of exactly 100 falls in the last one), with the number of Socios of each bin.
12. **Given** a simulation result, **When** it is shown, **Then** it includes, for both situations, the mean, the median, the standard deviation and the 10th and 90th percentiles of the totals (definitions in "Calculation definitions"), and their differences.
13. **Given** a simulation result, **When** it is shown, **Then** it includes how many Socios go up, how many go down and how many keep their position versus the ranking, the mean absolute change of position, and how many go up and how many go down in a relevant way (definitions in "Calculation definitions"). Unchanged Socios count in neither "up" nor "down".

*Flatness and saturation (question 4)*

14. **Given** a simulation result, **When** it is shown, **Then** for both situations it shows the number of Socios whose total is 100.00, the number of Socios that need a cap adjustment (their components add more than 100), the number of Socios tied with at least one other Socio at two decimals and the size of the largest tie.
15. **Given** the simulation puts at the cap at least as many Socios as the relevant movement threshold and more than the ranking has, **When** it is shown, **Then** the saturation alert `SATURATION_ALERT` appears, stating the number of Socios at 100 now and in the simulation and that their order would be decided by seniority and age. **Given** the standard deviation of the simulation is 80 % or less of the ranking's (and the ranking's is not 0), **Then** the flatness alert `FLATNESS_ALERT` appears with the percentage of drop. Both can appear at the same time; neither blocks anything.

*Change per component (question 3)*

16. **Given** a simulation result, **When** it is shown, **Then** it includes, for each component stored per Socio (`attendance_frequency`, `attendance_distance`, `institutional`, `seniority_age`, `new_member_bonus`, `cap_adjustment`) and for the total, the mean in the ranking, the mean in the simulation and the change, over all Socios of the ranking, with the labels of HU-16. The changes of the six components add up exactly to the change of the mean total.

*Effect of each parameter (question 3)*

17. **Given** a simulation, **When** it is shown, **Then** it lists the **changed parameters**: those whose hypothetical value differs from the value of the ranking's rules version, with both values. Parameters are grouped in four **factors**: pillar weights (`wA`, `wP`, `wT`, always together because they must add up to 1.00), distance weight inside attendance (`αA`), distance inflection (`dsat`), and **other parameters** (`Pinst_max`, `αT`, `Tref`, `Eref`, `γ`, `Bmax`, `Tmax`, `tcarencia`).
18. **Given** two or more factors changed, **When** the result is shown, **Then**, besides the full simulation, one additional simulation is run **for each changed factor among pillar weights, `αA` and `dsat`**, applying only that factor's hypothetical values over the values of the ranking's rules version. Each one reports the mean change of the total, the Socios that go up and go down, and the mean absolute change of position; they are ordered from the largest to the smallest mean absolute change of position (ties: pillar weights, `αA`, `dsat`), and the first is flagged as the factor that weighs most.
19. **Given** the isolated simulations of scenario 18, **When** they are shown, **Then** next to them a row "Resto: otros parámetros e interacciones" shows the mean change of the total of the full simulation minus the sum of the isolated ones, and lists the changed parameters that are not isolated (the factor "other parameters"). The effects of the factors are not additive in general, and the screen says so.
20. **Given** only one factor changed (including only "other parameters"), **When** the result is shown, **Then** no isolated simulation is run and the message `SINGLE_FACTOR` states that its effect is the one of the total. **Given** no factor changed, **Then** scenario 9 applies.
21. **Given** the isolated simulations are slower than the main result, **When** the Admin runs a simulation, **Then** the main result (scenarios 8 to 16 and the equity analysis of HU-30) is shown first and the effect by parameter is shown as soon as it is ready, with a "calculando" indicator in the meantime. **Given** the isolated simulations fail or do not finish within their target, **Then** the main result stays shown and the section shows `BREAKDOWN_UNAVAILABLE`.
22. **Given** an isolated simulation, **When** it is computed, **Then** it follows every rule of scenarios 6, 8 and 9: same validation, same calculation, same tiebreak, no real data modified. Any shortcut used to compute it MUST give exactly the same result as a full recomputation (parity test).

*Side by side, repetition and use*

23. **Given** any result, **When** it is shown, **Then** it is side by side with the current situation (before/after), labelled "Ranking actual" with its rules version and date, and "Simulación" with the changed parameters; the equity analysis of HU-30 is shown on the same screen, computed from the same hypothetical values; it is not a separate simulation.
24. **Given** a finished simulation, **When** the Admin changes the values, **Then** it can be repeated as many times as wanted; each run is independent and nothing accumulates between runs.
25. **Given** the simulator, **When** it runs, **Then** it does not require the real adjustment flow (HU-28) nor a new official calculation (HU-25), and it offers no control to apply the values: to make them official the Admin uses HU-28, which applies its own cut-off, lock and confirmation. The result lists the changed parameters with their previous and hypothetical values so they can be entered there.
26. **Given** a result shown, **When** the Admin asks to download it, **Then** a CSV file with the same figures as the screen is generated at that moment (format in "Export"). It is not stored anywhere, and the real data does not change.

---

### Edge Cases

- **No effect on real data**: scores, positions, rankings, rules versions and the lock never change. Nothing is persisted and no audit record is written, because nothing changes (cross-cutting section 6, audit).
- **Baseline**: "before" is the stored latest completed ranking, as stored (not recomputed), with its own rules version, which may differ from the rules in force; both are shown (scenarios 1 and 2).
- **Snapshot date**: the snapshot holds the values at the calculation date of the ranking. The simulation does not age the Socios, shift the attendance window or reflect later loads: it isolates the effect of the rules. The screen shows the date of the ranking.
- **Differs from HU-18 on purpose**: HU-18 refreshes the distance of the Socio who asks; HU-29 uses the snapshot for every Socio, so the only difference between "before" and "after" is the rules.
- **Zero-sum positions**: positions are a permutation of the same population, so for every Socio that goes up there is at least one that goes down. The number of Socios up and down is therefore always shown together with the magnitude (mean absolute change of position and relevant movements).
- **Changing the three pillar weights**: they are one factor because each weight alone breaks the sum rule; the effect of each weight is read in the change per component (scenario 16).
- **Equity analysis**: shown next to these results (HU-30).
- **Scope**: only the Socios and data of the latest completed ranking.
- **Other formulas**: written for the components of the scoring model v1. With a second formula in the catalog, components and parameter groups come from its descriptor (README, open items).
- **Access**: any Admin of the club.

## Calculation definitions *(mandatory)*

- **Total**: the 2-decimal total stored per entry (scoring model, rule 1). All statistics are computed on 2-decimal totals and displayed rounded half up to 2 decimals; comparisons and thresholds use the exact values.
- **Mean / standard deviation**: arithmetic mean; population standard deviation (divisor `N`).
- **Median**: the middle total; with an even `N`, the mean of the two middle ones.
- **Percentile `p`** (10 and 90): nearest-rank method: the total at position `ceil(p/100 · N)` of the totals in ascending order.
- **Change of position** of a Socio: `ranking position − simulated position`. Positive means it goes up (a better, lower position number); negative, it goes down; 0, unchanged.
- **Mean absolute change of position**: mean of the absolute change of position, displayed with one decimal, half up.
- **Relevant movement** (fixed in the product): a change of at least `m = max(1, ceil(N / 100))` positions, that is 1 % of the ranking. "Up in a relevant way" is a change `≥ +m`; "down in a relevant way", `≤ −m`. HU-30 uses the same `m`.
- **At the cap**: total equal to 100.00. **Needs a cap adjustment**: component `cap_adjustment` lower than 0.
- **Tied**: a Socio whose 2-decimal total equals that of at least one other Socio. Their order is decided by the tiebreak.
- **Saturation alert** (fixed values): the simulation has at least `m` Socios at the cap and more than the ranking has.
- **Flatness alert** (fixed values): standard deviation of the simulation `≤ 0.80 ×` that of the ranking, the latter being greater than 0. The percentage shown is `100 × (1 − ratio)`.
- **Factors**: pillar weights, `αA`, `dsat`, other parameters (scenario 17). The values compared are `Decimal`s (scoring model, rule 8).
- Fixed values can only be changed by amending this spec.

## Messages and codes *(mandatory)*

Texts in Spanish (es-AR), produced by the server. Errors answer like HU-27 (`{"detail": {"code", "message", ...}}`).

| Situation | HTTP | Code | Message |
|---|---|---|---|
| No completed ranking | 409 | `NO_BASELINE` | Todavía no hay un ranking calculado, así que no hay con qué comparar. Calculá el ranking para poder simular. |
| Ranking without Socios | 409 | `EMPTY_RANKING` | El último ranking no tiene socios: no hay nada para simular. |
| Invalid values | 422 | `INVALID_VALUES` | Hay valores que no se pueden simular. Corregilos y volvé a intentar. Also returns `violations`, a list of `{code, parameter, message}` with the codes and texts of HU-27. |
| Ranking of the result no longer available (effect by parameter or CSV of a ranking that is not a `completed` ranking of the club) | 409 | `BASELINE_NOT_FOUND` | El ranking de esta simulación ya no está disponible. Volvé a simular. |
| Forbidden (Socio) | 403 | `FORBIDDEN` | (existing code) |
| Admin without club | 403 | `ADMIN_WITHOUT_CLUB` | (existing code) |
| Unauthenticated | 401 | `NOT_AUTHENTICATED` | (existing code) |
| Baseline line (always shown) | — | — | Comparado con el ranking calculado el {dd/mm/aaaa hh:mm} (reglas versión {n}). |
| Rules in force differ | — | — | Las reglas vigentes (versión {v}) son distintas de las del ranking (versión {n}). Podés cargarlas acá para ver cómo cambiaría el ranking en el próximo cálculo. |
| Values equal to the ranking's | — | `NO_CHANGES` | Los valores son iguales a los del ranking: no hay diferencias para mostrar. |
| Saturation alert | — | `SATURATION_ALERT` | Con estos valores {a} socios llegarían al tope de 100 (hoy {b}). Entre ellos el orden lo definirían la antigüedad y la edad. |
| Flatness alert | — | `FLATNESS_ALERT` | Con estos valores los puntajes se concentran: la dispersión baja un {x} %. |
| Only one factor changed | — | `SINGLE_FACTOR` | Cambiaste un solo grupo de parámetros: su efecto es el del resultado total. |
| Non-additivity note | — | — | Los efectos de cada grupo no se suman: al combinarlos interactúan. |
| Effect by parameter not available | — | `BREAKDOWN_UNAVAILABLE` | No pudimos calcular el efecto de cada parámetro. El resultado general sigue siendo válido. |
| Calculating the effect by parameter | — | — | Calculando el efecto de cada parámetro… |
| Factor that weighs most | — | — | Es el que más mueve el ranking. |

## Export *(mandatory)*

- UTF-8 with BOM, one header row, decimal point, comma as separator; name `simulacion-reglas-AAAAMMDD-HHMM.csv` (Buenos Aires time of the download).
- Columns: `seccion`, `elemento`, `antes`, `despues`, `diferencia`. One row per figure shown on the screen, in the order of the screen; empty cells where a column does not apply.
- Sections: `contexto` (ranking date, rules versions), `parametros` (changed parameters: `antes` = value of the ranking, `despues` = hypothetical), `resumen` (mean, median, standard deviation, percentiles, up, down, unchanged, relevant movements, mean absolute change), `histograma`, `saturacion`, `componentes`, `parametro_aislado` (including the "Resto" row), and, from HU-30, `perfil`, `segmento` and `veredicto`.
- Only sections that were shown are included; a section that was unavailable is omitted. The file contains aggregates only, never data of an individual Socio.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept hypothetical values for any parameter of the scoring model and pre-fill them with the rules version of the latest completed ranking, offering to load the rules in force when they differ.
- **FR-002**: System MUST validate them with the same limits, sum rule, decimal arithmetic, codes and texts as HU-27 and HU-28, returning all violations together, and MUST NOT apply the season cut-off or the formula lock to a simulation.
- **FR-003**: System MUST compute the simulated result from the inputs snapshot of the latest completed ranking, with the same calculation and tiebreak as HU-25, without modifying any real data and without re-reading source data.
- **FR-004**: System MUST show, for both situations, the histogram in 20 bins of 5 points, the mean, median, standard deviation and the 10th and 90th percentiles.
- **FR-005**: System MUST show the number of Socios that go up, go down and keep their position, the mean absolute change of position and the relevant movements.
- **FR-006**: System MUST show, for both situations, the Socios at the cap of 100, those needing a cap adjustment, the tied Socios and the largest tie, and the saturation and flatness alerts when they apply.
- **FR-007**: System MUST show the mean per component and total in both situations and their change, with the changes of the components adding up to the change of the total.
- **FR-008**: System MUST list the changed parameters with their previous and hypothetical values and, when two or more factors changed, simulate on its own each changed factor among pillar weights, `αA` and `dsat`, report the effect of each, order them by impact, flag the one that weighs most and show the remainder with the non-isolated parameters.
- **FR-009**: System MUST show the effect by parameter after the main result without blocking it, and keep the main result when the effect by parameter fails.
- **FR-010**: System MUST always show results side by side with the current situation, with the rules version and date of the ranking, and show the equity analysis of HU-30 on the same screen from the same simulation.
- **FR-011**: System MUST NOT require HU-28 or HU-25 to run a simulation, MUST NOT apply values to the real rules, and MUST allow unlimited repetition.
- **FR-012**: System MUST use a single ranking per result (the latest completed one when the run starts) and show its date and rules version.
- **FR-013**: System MUST reject non-Admin users, Admins without club, and unauthenticated requests, and read only the ranking of the Admin's club.
- **FR-014**: System MUST generate on demand a CSV file with the figures shown, with the format of "Export", without storing it.
- **FR-015**: System MUST return the main result within the target in cross-cutting section 6 and the effect by parameter within the target of the success criteria.
- **FR-016**: System MUST give each user-facing message the exact text and code of "Messages and codes".

### Key Entities

- **RulesSimulation**: baseline ranking (id, calculation date, rules version), hypothetical values and changed parameters, simulated totals, components and positions, comparison with the ranking (distribution, statistics, movement, saturation, components), factor simulations (`FactorEffect`), and the equity analysis of HU-30 (`EquitySegment`, `MoverProfile`, verdict). Transient.
- **FactorEffect**: factor (pillar weights, `αA`, `dsat`), its changed parameters, mean change of the total, Socios up and down, mean absolute change of position. Transient, part of the RulesSimulation.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 real scores, positions, rankings, rules versions or locks change as a result of any simulation.
- **SC-002**: 100% of results are shown next to the current situation, with the rules version and date of the ranking.
- **SC-003**: Parity test: with the same data and the same calculation date as the baseline ranking (the date injected in the test), applying the simulated values in HU-28 and running HU-25 gives exactly the simulated components, totals and positions of every Socio. The same test holds for each isolated simulation of a factor, applied on its own.
- **SC-004**: Identity test: with hypothetical values equal to those of the ranking, 100% of simulated components, totals and positions equal the stored ones.
- **SC-005**: 95% of the main results return within 3 seconds up to 50,000 Socios and within 10 seconds up to 500,000 (cross-cutting section 6), equity analysis included.
- **SC-006**: 95% of the effects by parameter return within 9 seconds up to 50,000 Socios and within 30 seconds up to 500,000, with up to three isolated simulations (proposed targets, to validate with a load test as the others of cross-cutting section 6).
- **SC-007**: In 100% of results, the changes per component add up to the change of the mean total, the histogram counts add up to `N`, and up + down + unchanged equal `N`.
- **SC-008**: 100% of invalid inputs are rejected with all their violations, and 0 simulations run with the weights not adding up to 1.00.

## Assumptions

- Baseline ("before") is the stored latest completed ranking, computed with its own rules version, which may differ from the rules in force; both are displayed.
- Decided: all matrix parameters can be simulated because the inputs snapshot contains raw values, not only pillar scores. The three pillar weights form one factor to isolate because of the sum rule; the remaining changed parameters are reported together as "other parameters" and are not isolated, which keeps the extra computation to at most three simulations.
- Decided: the simulator never applies values. The Admin enters them in HU-28, so HU-28 does not change; the CSV (scenario 26) is the way to carry the evidence out, since nothing is stored and a stored report (HU-42) is outside the MVP.
- Decided: the thresholds of this spec (1 % relevant movement, saturation, 80 % flatness) are fixed in the product, like the factors of the formula; they are not settings.
- Volume: up to 500,000 Socios; the targets are in cross-cutting section 6 and call for computing in memory over the stored snapshot. A factor simulation may reuse the pillars already computed (for example, a change of weights only recombines them) as long as the result is identical to a full recomputation (scenario 22).
- The simulation is deterministic: same ranking and same values always give the same result.

## Revision Notes (v4)

- v2: Defined baseline, histogram bins, tiebreak in simulated positions, validation, parity test and performance target. v3: volume target added.
- v4: pre-fill and notice when the rules in force differ from the ranking; codes and texts (no more "informative message" nor "same messages as HU-28", which has none); validation reuses the codes of HU-27; the simulator works with the formula locked or after the season cut-off; empty ranking, permissions and tenancy; identity and parity conditions; single ranking per result.
- v4: results extended: dispersion and percentiles, relevant movement, saturation and ties with alerts, change per component, effect of each factor on its own with the remainder, side-by-side labels, non-blocking delivery of the breakdown, CSV export, and ownership of the equity analysis of HU-30. Histogram bounds, rounding, median and percentile definitions fixed.
- v4: performance target now consistent with cross-cutting section 6 (it said "expected volume").
- v4: `BASELINE_NOT_FOUND` added to "Messages and codes" (effect by parameter and CSV ask for the ranking of the result shown, scenario 10).

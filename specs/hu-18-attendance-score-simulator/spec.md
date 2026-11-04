# Feature Specification: Estimated Score Simulator by Attendance

**Feature Branch**: `hu-18-attendance-score-simulator`
**Created**: 2026-10-11 | **Revised**: 2026-11-02 (v5)
**Status**: Draft
**Backlog Reference**: HU-18 (Estimate: 8, Priority: Media, MVP: Yes). Re-estimate: the position of a Partido is now a probabilistic range with its own validation (see Revision Notes).
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Socio of the club, I want to simulate how attending or not attending the next event would affect my score, so that I can anticipate the impact of my decision on my total score."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Estimated Score Simulator by Attendance (Priority: P2)

As a Socio of the club, I want to simulate how attending or not attending the next event would affect my score, so that I can anticipate the impact of my decision on my total score.

**Why this priority**: Makes the effect of the scoring rules tangible and encourages attendance.

**What the Socio sees**:

- **The projected score for both hypotheses, from the official calculation.** It is the part that can be stated without reservations: it is exactly what the official calculation gives from the data of the latest ranking, with the Socio's current distance, plus this event.
- **For a Partido, the position as a range, labeled as an estimate.** A range says what is known; a single number would pretend a precision that does not exist, because the other Socios have not yet decided what they will do. It is shown by default; the Admin of the club can turn it off (scenario 14).
- **For an institutional event, the notice that not attending leaves the score unchanged but the position can drop.** The position itself is not estimated for these events in this version (see "Position model").

**Independent Test**: As a Socio, pick an upcoming Partido and verify the projected score if attending and if not attending (attending raises or keeps it; not attending never raises it above the score recomputed with the same distance), that the real score is unchanged, that each position is a labeled range, and that the position of attending is never worse than the position of not attending. Change the Socio's distance (club roster) and verify that the projections use the new one while the current total and position keep the ranking's. Pick an institutional event and verify the two scores and the notice, with no position. Verify that the position projection is on for a new club, then turn it off as Admin and verify that the next simulation shows only the scores.

**Acceptance Scenarios**:

*Selection*

1. **Given** a logged-in Socio in the latest completed ranking and available upcoming events, **When** they select one event, **Then** the simulation for that event starts. The simulation covers only that event; other upcoming events are not combined with it.
2. **Given** a Socio not in the latest completed ranking (joined afterwards, overdue fees, or no ranking ever calculated), **When** they open the simulator, **Then** the message "Para simular necesitás un puntaje calculado. Todavía no estás en el ranking." is shown (`NOT_IN_RANKING`).
3. **Given** the Socio selects an event that is no longer `published` or whose start has passed, **When** the simulation is requested, **Then** it is rejected with "Este evento ya no está disponible para simular." (`EVENT_NOT_SIMULABLE`) and nothing is calculated.

*Projected score (exact)*

4. **Given** a selected event of type **Partido**, **When** the simulation runs, **Then** the system shows the projected total if the Socio attended: the event is added to both the attended and the total counts of its class with its factor C(I), and the distance term is recomputed, under the rules version of the latest ranking and with the Socio's current distance (scenario 9).
5. **Given** the same Partido, **When** it runs, **Then** the system shows the projected total if the Socio did not attend: the event is added only to the total count of its class, so the frequency term falls.
6. **Given** a selected event of type **Evento institucional/amateur**, **When** the simulation runs, **Then** attending adds the points defined for that event at its publication to the Socio's participation points before the cap `Pinst_max` is applied, and not attending leaves the event without effect on the score.
7. **Given** any simulation, **When** it completes, **Then** the current total, both projections and the difference of each with the current total are shown, each capped at 100, and the Socio's real score is not modified.
8. **Given** any simulation, **When** it is shown, **Then** the rules version of the latest ranking is shown, together with the date of that ranking. When the rules in force differ from those of the ranking, it also says that the rules in force apply from the next calculation (text in "Messages").
9. **Given** the club has sent a new distance to the stadium for the Socio (a change of home) after the latest ranking was calculated, **When** the simulation runs, **Then** both projections use the **current** distance, while the current total and the current position stay those of the ranking, which used the old one. The difference of each projection is still taken against the current total, so it includes the effect of the new distance, and the screen says so (text in "Messages"). Only the Socio's own distance is refreshed: every other Socio stays as the ranking has them.

*Position (estimated range, Partido only)*

10. **Given** a selected Partido whose position can be estimated, **When** the simulation is shown, **Then** next to the current position (exact, from the ranking) it shows, for each hypothesis, an estimated position and a probable range, for example "puesto estimado 118 (probable entre 112 y 125)", computed as defined in "Position model", with the estimate label (text in "Messages") on the same screen.
11. **Given** a selected institutional event, **When** the simulation is shown, **Then** it shows the two projected scores, the current position of the ranking and the notice that not attending leaves the score unchanged but the position can drop (text in "Messages"). No estimated position and no error message are shown; the response carries the reason code `INSTITUTIONAL_NOT_ESTIMATED`.
12. **Given** a selected Partido whose position cannot be estimated (projection not enabled for the club, not enough history, ranking too small, or a failure while computing it), **When** the simulation is shown, **Then** only the scores are shown, with the message "No podemos estimar tu posición en este momento. Te mostramos solo tu puntaje." (`POSITION_NOT_AVAILABLE`). The reason is returned as a code, never as a different message.
13. **Given** any estimated position, **When** it is shown or returned, **Then** it is never shown without the estimate label and never as a single exact number.

*Settings of the club (Admin)*

14. **Given** an Admin of the club, **When** they read or change the simulator settings (`position_projection_enabled`, `position_range_level`, `position_prior_strength`, `position_min_population`), **Then** only the settings of their own club are read or changed, only the fields sent change, an invalid value is rejected without changing anything, the change is audited with the previous and new values, and the next simulation already uses the new values. The projection is on by default. A Socio cannot read or change the settings.

---

### Edge Cases

- **No upcoming events**: same empty state as HU-17 ("No hay eventos próximos publicados.").
- **Repeat simulations** never accumulate effects.
- **Event not in the denominator**: upcoming events are not part of the current score (only events with loaded attendance count), so the current total is the baseline.
- **Event class**: the class of a Partido and its factor C(I) are used in the calculation but are not shown on this screen, in line with HU-17 (the class is not shown to Socios). The screen says only "Partido".
- **Distance on attending**: the Socio has one distance to the stadium (data contract), so the mean distance credit does not change when the Socio had already attended matches. It does change when the Socio had attended none (`N_asistidos` goes from 0 to 1).
- **Cap of the participation pillar**: attending an institutional event adds its points before the cap, so the gain can be smaller than the points of the event (or zero) when the Socio is near or at `Pinst_max`. In that case both hypotheses can show the same score.
- **Position of attending vs. not attending**: attending never gives a worse estimated position than not attending (the projected score is never lower, and every other Socio is treated the same in both). When both scores are equal, both ranges are equal.
- **Change of home**: the distance comes from the Socio's current record sent by the club (HU-43); the Socio does not edit it. The projections use it, the ranking keeps the old one until the next calculation. With the same distance in both, the not-attending score is never above the current total; with a nearer or farther home it can be, and the difference shown includes that change. If the current record is missing, the distance of the ranking is used.
- **Other personal data** (age, seniority, fee status) is not refreshed: it stays as in the ranking and falls under "Other changes are not captured".
- **Other changes are not captured**: a change of fee status, Socios who join or leave, other events between today and the next calculation, loads of attendance, the expiry of old participation and the shifting of the window, the daily decay of the new-member bonus, the aging of seniority and age, and the date of the next calculation (which the system does not know). Some are deterministic but depend on that date. For this reason the position is always an estimate, and the scores are the official calculation **over the data of the latest ranking**, not a forecast of the next ranking.
- **Ranking too small, or no club history**: see "When the position is not estimated".
- **Privacy**: the response contains the Socio's own data and aggregate estimates only. Nothing identifies another Socio, their score, their distance or their probability.
- **The position is secondary**: if it cannot be computed, the score projections are still shown (scenario 12).

## Position model *(mandatory)*

The estimate is a closed-form calculation over the stored ranking. It does not simulate thousands of runs. It is deterministic: the same ranking, event and settings always give the same range.

**Scope of this version: Partido only.** The probability of attending an institutional event needs, for each Socio, how many institutional events they could have attended in the window, and the inputs snapshot does not hold that number. Estimating the position of an institutional event is therefore outside this version (scenario 11) and needs a later revision of this spec and of the snapshot. It is not activated automatically.

**Population.** Every Socio of the latest completed ranking of the club, except the Socio asking. The ranking has `N` ranked Socios.

**Two outcomes per other Socio.** For each other Socio `j`, and for the selected Partido, the official calculation (the same engine as HU-25, with the rules version of the ranking, applied to `j`'s inputs snapshot as the ranking has it) gives two totals:

- `A_j`: `j` attends the Partido (same rules as scenario 4).
- `B_j`: `j` does not attend (same rules as scenario 5).

`A_j` is never lower than `B_j`.

**"Above".** A total for `j` is above the Socio's hypothetical total when it comes before it in the ranking order of HU-25: higher total at two decimals, and if equal, greater seniority, then greater age (exact dates of the snapshot), then lower document number (as a number). The Socio's own hypothetical total is placed with their own keys and their current distance (so it can differ from their place today even apart from the event, if their distance changed). So there is no "approximate" position because of ties.

**Probability that `j` ends above.**

```
q_j = p_j · [A_j above] + (1 − p_j) · [B_j above]        ([·] is 1 when true, 0 when false)
```

`p_j` is the probability that `j` attends the Partido (next section).

**Position, mean and spread.** For a hypothesis of the Socio (attending or not attending):

```
μ = Σ_j q_j                          estimated position = 1 + μ, rounded half up
σ² = Σ_j p_j · (1 − p_j)             only over the Socios with [A_j above] = 1 and [B_j above] = 0
range = [ max(1, floor(1 + μ − z·σ)),  min(N, ceil(1 + μ + z·σ)) ]
```

- Only the Socios close to the Socio's total add uncertainty. Those whose two outcomes are on the same side are above or below with certainty and add nothing to `σ`. Since `A_j ≥ B_j`, the only mixed case is `A_j` above and `B_j` not above.
- `z` is the two-sided normal quantile of the range level (setting `position_range_level`, default 80 %, `z = 1.2816`). The range is rounded outward (floor and ceil) so it never gets narrower than computed.
- If the lower and upper limits are equal, the screen shows the single number, still labeled as an estimate.
- The decisions of different Socios are treated as independent. The real behavior is positively correlated (a big match moves many Socios at once), which makes the true spread larger than `σ`. This is the main thing the validation below must check.
- Both hypotheses use the same `p_j`.
- The model needs one calculation of `A_j` and `B_j` for every other Socio. They do not depend on who is asking, so they may be computed once per (ranking, event) and reused; the result is identical.

**Probability `p_j` of attending, smoothed.**

```
p_j = ( a_j + k · r ) / ( n_j + k )
```

- `a_j` and `n_j` are the matches of the Partido's class `c` that Socio `j` attended and the matches of that class counted for them (snapshot: `attended_by_class`, `matches_by_class`).
- `r` is the club rate of that class: attended / counted, summed over all ranked Socios. If the club has no counted match of class `c`, `r` is the club rate over all classes. If it has none at all, the position is not estimated.
- `k` is the weight of the club rate (setting `position_prior_strength`, default 5). A Socio with little history takes mostly the club rate; a Socio with one match attended cannot get probability 100 %.

**Data it reads (from the ranking, except one datum).** Per ranked Socio: the per-class counts, the distance, the raw participation points (before the cap), the exact seniority start and birth date, `T`, `E`, `t`, the previous-baja interval, the DNI of the entry's Socio and the entry's total. Of the ranking: the rules version, the calculation date, `N`. Of the event: type, class, start, state. The only datum read outside the ranking is the **current distance of the Socio asking**, from the club's roster copy; the other Socios are always taken from the ranking.

### When the position is not estimated

For a Partido, the position is not estimated (scenario 12) when any of these holds:

1. `position_projection_enabled` is off for the club. It is on by default; the Admin can turn it off (scenario 14).
2. The club has no counted match in the window (see `r`).
3. The ranking has fewer than `position_min_population` Socios (default 100): the club rates are too noisy.
4. The calculation fails or does not finish within the response time.

Codes: `PROJECTION_DISABLED`, `INSUFFICIENT_HISTORY`, `SMALL_POPULATION`, `POSITION_ERROR`. For an institutional event the code is `INSTITUTIONAL_NOT_ESTIMATED` (scenario 11).

## Validation of the position *(recommended)*

The range is only worth showing if it is right as often as it says. The projection is on by default anyway: the simulation never changes the real ranking or any stored data (FR-004), and every estimated position carries the estimate label (scenario 13), so a range that is less accurate than it says misleads the Socio's expectation but not their real place. To check it, the team replays the calculation on past dates and compares it with what really happened. This is an offline procedure of the team, with no screen, and it is not a condition to show the position.

**Replay.** For each of at least 5 past reference dates `D`, each followed by a Partido with loaded attendance: rebuild the inputs as of `D` from the events, attendance and activities the system keeps (nothing is deleted; replaced loads stay in the history), compute the official ranking at `D`, run this simulation for that Partido on that ranking, and compare with the official ranking calculated the day after the Partido from the same kept data. The comparison uses the hypothesis that matches what each Socio did. Stored rankings are not used: the history of rankings is outside the MVP. Fields the roster overwrites (distance, fee status) take their current values; this is an approximation that the team records.

**Measures.**

| Measure | Question | Pass |
|---|---|---|
| Coverage of the range | How often is the real position inside "probable entre X y Y"? | within 5 percentage points of `position_range_level` (for 80 %: from 75 % to 85 %). Below means the model is too optimistic; well above means ranges that are uselessly wide |
| Mean absolute error of the estimated position | Compared with the simple version (every other Socio frozen at today's total) | strictly lower than the simple version. If it does not improve, the complexity is not worth it |

The pass limits are adopted values; changing them is an amendment of this spec. The result, the dates, the sample and the settings used are recorded with the decision. It is worth repeating the replay when the club's formula is replaced (HU-27) or when there is enough new data. If it fails, the team recommends that the Admin tune `k` or the range level with the values the replay suggests, or turn the projection off so that the Socios see only scores (scenario 14).

## Messages *(mandatory)*

| Where | Code | Text (es-AR) |
|---|---|---|
| Socio not in the ranking | `NOT_IN_RANKING` | "Para simular necesitás un puntaje calculado. Todavía no estás en el ranking." |
| Event not simulable | `EVENT_NOT_SIMULABLE` | "Este evento ya no está disponible para simular." |
| Position of a Partido not estimated | `POSITION_NOT_AVAILABLE` | "No podemos estimar tu posición en este momento. Te mostramos solo tu puntaje." |
| Estimate label, beside every estimated position | — | "Estimación: supone que cada socio asiste según su propio historial. Puede diferir después del próximo cálculo." |
| Institutional events | — | "No asistir no cambia tu puntaje, pero tu posición puede bajar si otros socios suman puntos." |
| Rules in force differ from the ranking | — | "Esta simulación usa las reglas del último ranking (versión {n}). Las reglas vigentes se aplicarán desde el próximo cálculo." |
| Distance changed since the ranking | — | "Tu distancia al estadio cambió desde el último ranking: la simulación usa {nuevo} km y tu puntaje de hoy usa {anterior} km." |
| Range line | — | "puesto estimado {n} (probable entre {lo} y {hi})", numbers with es-AR thousands separator |

"Probable" means the configured range level; the detail of the screen states the percentage.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let the Socio select an upcoming published event to simulate, and MUST reject an event that is not published or has started (`EVENT_NOT_SIMULABLE`).
- **FR-002**: System MUST calculate the projected total if attending, with the official calculation over the stored inputs snapshot, the Socio's current distance and the rules version of the latest ranking, for both event types.
- **FR-003**: System MUST calculate the projected total if not attending.
- **FR-004**: System MUST NOT modify the Socio's real score or any stored data.
- **FR-005**: System MUST show the rules version and the date of the ranking used, and cap results at 100.
- **FR-006**: System MUST show, for a Partido and per hypothesis, the estimated position as a range computed with the position model, always with the estimate label, and MUST show the current position next to it.
- **FR-007**: System MUST estimate the position of a Partido only when `position_projection_enabled` is on for the club and the conditions of "When the position is not estimated" hold; otherwise it MUST show only the scores with `POSITION_NOT_AVAILABLE`.
- **FR-008**: System MUST show, for an institutional event, the two scores, the current position and the notice about the position, and MUST NOT estimate its position (`INSTITUTIONAL_NOT_ESTIMATED`).
- **FR-009**: System MUST NOT reveal the score, probability or any datum of another Socio, and MUST read only the ranking of the Socio's own club (cross-cutting section 9).
- **FR-010**: System MUST take the settings `position_projection_enabled` (on by default), `position_range_level`, `position_prior_strength` and `position_min_population` from the club's settings (cross-cutting section 8).
- **FR-011**: System MUST use the Socio's current distance in both projections when it differs from the one of the ranking, keep the current total and position from the ranking, and show the notice about the difference. Other Socios MUST be taken as the ranking has them.
- **FR-012**: System MUST NOT show the class or the factor of a Partido on this screen.
- **FR-013**: System MUST let an Admin read and change the settings of FR-010 for their own club only (the club comes from the account, cross-cutting section 9), changing only the fields sent. It MUST reject, without changing anything, a range level outside the open interval from 0 to 1 or with more than 2 decimals, a weight `k` that is not greater than 0 (with 0, a Socio without history would divide by zero), and a minimum population lower than 1. It MUST audit each change with who, when and the previous and new values; a request that changes nothing is not audited. A Socio MUST NOT read or change them.

### Key Entities

- **AttendanceSimulation**: Socio, event (type, points for an institutional event), ranking and its calculation date, rules version, current total, current position, distance used and distance of the ranking, per hypothesis (attending, not attending): projected total, difference, estimated position (estimate, lower, upper) or none with its reason code, range level. Transient.
- **Settings of the club** (cross-cutting section 8): `position_projection_enabled` (on), `position_range_level` (0.80), `position_prior_strength` (5), `position_min_population` (100). Edited by the Admin (FR-013).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of simulations leave the real score and stored data unchanged.
- **SC-002**: Projected scores equal what the official calculation would give if the Socio attended or not, in a parity test with the same inputs (the snapshot with the Socio's current distance) and the same event: recalculating the ranking with that distance and the event gives the same score.
- **SC-003**: 100% of estimated positions are ranges and carry the estimate label.
- **SC-004**: In 100% of simulations the score of attending is equal or higher than that of not attending, the estimated position of attending is equal or better, and, with an unchanged distance, for an institutional event the score of not attending equals the current one.
- **SC-005**: 0 responses contain data of another Socio.
- **SC-006**: 100% of the Admin's changes to the settings apply from the next simulation, are audited, and never affect another club.
- **SC-007**: 95% of simulations respond within 2 seconds (cross-cutting section 6), up to 500,000 Socios; otherwise the scores are shown without the position.
- **SC-008**: In a test with a fixed ranking, the mean, the spread and the range reproduce a hand-computed case (including a Socio with one match attended, ties resolved by the tiebreak, and a club without history for the class).
- **SC-009**: 100% of institutional simulations show no estimated position and carry the notice.

## Assumptions

- Uses the inputs snapshot stored by HU-25, so no source data is re-read, except the Socio's own current distance. For a Partido it needs, per entry: the per-class counts of matches counted and attended, the distance, the raw participation points, the exact seniority start and birth date, `T`, `E`, `t` and the previous-baja interval. The ranking calculation already keeps them to compute and order the ranking; this spec does not change HU-25.
- The simulation assumes the rest of the Socio's data does not change. The distance is the exception because a change of home is known to the system and the Socio expects the projection to reflect it.
- Decided by the product owner: the position cannot be known exactly; for a Partido it is shown as a labeled probabilistic range, with the score as the only exact figure. It is shown by default, without a prior validation, because the simulation never changes the real ranking; the Admin can turn it off. Institutional events show scores and the notice.
- The decisions of the Socios are treated as independent and each one attends with their smoothed historical rate; the validation measures how far that holds.
- The settings (`k` = 5, range 80 %, minimum 100 Socios) and the pass limits are adopted defaults; the replay can show that a club needs other values, which are then set in its settings.

## Worked example (illustrative)

The Socio is 1200 km from the stadium, 10 years a member, 45 years old. In the window: attended 3 of 4 Clase A, 6 of 10 Clase B, 5 of 6 Clase C; 70 participation points (an assembly of 40 and 3 months of federated sport). Score 59.55 (34.19 + 4.41 + 14.00 + 6.95), as in the scoring model worked example. The scores below are exact with the formula. The population is synthetic (10,000 other Socios, invented), so the positions only show the mechanics, not real magnitudes of a club.

**Next match.** It is a Clase B match (factor 1.3, used in the calculation and not shown). Weighted frequency 19.8 of 27.8 today. Attending: 21.1 of 29.1 → 60.16. Not attending: 19.8 of 29.1 → 58.02. The distance term does not change (he already attended matches).

```
Partido                                            Reglas: versión 1
Tu puntaje hoy: 59,55          Tu posición hoy: 3.282

                      Si vas               Si no vas
Puntaje               60,16  (+0,61)       58,02  (−1,53)
Posición estimada     ~3.150               ~3.649
Rango probable        3.136 a 3.164        3.635 a 3.663

Estimación: supone que cada socio asiste según su propio historial.
Puede diferir después del próximo cálculo.
```

**Institutional event: an assembly of 40 points.** Attending adds 40 to 70 and the pillar is capped at 100, so the participation component goes from 14.00 to 20.00 (+6.00) and not 8.00.

```
Evento institucional                               Reglas: versión 1
Tu puntaje hoy: 59,55          Tu posición hoy: 3.282

                      Si vas               Si no vas
Puntaje               65,55  (+6,00)       59,55  (sin cambios)

No asistir no cambia tu puntaje, pero tu posición puede bajar
si otros socios suman puntos.
```

## Revision Notes (v5)

- The position projection is **on by default** for every club, and the validation is recommended, not a condition to show the position: the simulation never changes the real ranking or stored data, and every estimated position carries the estimate label. Decided by the team (decision 43).
- The Admin reads and changes the four settings of their own club (scenario 14, FR-013), with validation and audit. Before, there was no screen and only the team turned the projection on.
- SC-006 now measures the settings change instead of the recorded validation.

## Revision Notes (v4)

- The estimated position is no longer "the projected score placed among the current scores with the others frozen". For a Partido it is a probabilistic range: each other Socio attends with a smoothed probability from their own history, and the position is 1 plus the sum of the probabilities of ending above. Closed-form, with the tiebreak, so no "approximate position" for ties.
- Institutional events: scores and the notice only; their position is not estimated in this version because the inputs snapshot does not hold the number of institutional events each Socio could attend.
- Added the exact figure/estimate split, the cut to scores only, the settings, the exact messages and codes, the privacy rule and the invariants.
- Added the validation as a condition to publish the position, designed to run without a history of rankings (outside the MVP).
- The projected scores are the official calculation over the data of the latest ranking; they are not a forecast of the next ranking. The estimate label covers both.
- The projections use the Socio's current distance (change of home) while the current total and position stay those of the ranking; only the Socio's own distance is refreshed.
- The class and factor of a Partido are not shown, consistent with HU-17.
- v3: added the estimated position (labeled), support for institutional/amateur events and type-specific behavior. v4 replaces its position rule and removes decision 13's "holds the other Socios constant".

# Feature Specification: Rankings by Score Pillar

**Feature Branch**: `hu-44-pillar-rankings`
**Created**: 2026-11-18 | **Revised**: 2026-11-19 (v3)
**Status**: Draft
**Backlog Reference**: HU-44 (Estimate: 3, Priority: Media, MVP: Yes). Not in `Backlog - US.csv` yet; the estimate rests on HU-25 already storing every component per Socio.
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an Admin, I want a ranking for each pillar of the score to be produced when the rankings are calculated, so that I recognize the best Socios by type of participation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Top 10 by Pillar (Priority: P2)

As an Admin, I want a ranking for each pillar of the score to be produced when the rankings are calculated, so that I recognize the best Socios by type of participation.

**Why this priority**: It recognizes participation without changing the ranking or the waves; the general ranking (HU-25) stays the only one that orders access.

**Independent Test**: With the HU-25 control dataset, run the calculation and verify that each of the three tables matches the expected order of its pillar, that each Socio's pillar points equal their HU-16 breakdown, and that a Socio cannot read the tables.

**Acceptance Scenarios**:

1. **Given** a `completed` ranking, **When** the Admin opens the "Calcular ranking" tab, **Then** they see three tables with the top 10 of **Asistencia**, **Participación institucional** and **Antigüedad y edad**.
2. **Given** those tables, **When** they render, **Then** each row shows the position in the pillar (1 to 10), the Socio's name, their membership number and their points in the pillar with two decimals.
3. **Given** those tables, **When** they render, **Then** above them are shown the rules version and the date and time (in force since) of the ranking that produced them.
4. **Given** a Socio, **When** their points in a pillar are shown, **Then** they equal exactly their HU-16 breakdown: Asistencia is `asistencia – frecuencia` plus `asistencia – distancia`; Participación institucional and Antigüedad y edad are their single components.
5. **Given** a Socio with a new-member bonus or a cap adjustment, **When** the pillar rankings are built, **Then** neither counts in any pillar, so the sum of their three pillars can differ from their total (HU-14).
6. **Given** two Socios with the same points in a pillar, **When** positions are assigned, **Then** the tie is broken by greater seniority, then greater age, then lower document number (HU-25), so positions in a pillar are unique.
7. **Given** a pillar where fewer than 10 Socios have more than 0.00 points, **When** the table renders, **Then** only those Socios are listed, with no filler rows.
8. **Given** a pillar where no Socio has more than 0.00 points, **When** the table renders, **Then** it shows "Ningún socio sumó puntos en este pilar en el último cálculo." instead of an empty table.
9. **Given** no ranking has ever completed for the club, **When** the Admin opens the tab, **Then** "Todavía no hay un ranking calculado." is shown instead of the tables.
10. **Given** a calculation `running`, **When** the Admin opens the tab, **Then** the tables of the latest `completed` ranking are still shown, labelled "actualizando"; if there is none, scenario 9 applies with the same label.
11. **Given** a calculation that ends `failed`, **When** the Admin opens the tab, **Then** the tables of the latest `completed` ranking are shown unchanged.
12. **Given** a Socio session, or no session, **When** the pillar rankings are requested, **Then** the server rejects the request (403 / 401) and the Socio portal has no such screen.

---

### Edge Cases

- **Source**: the three rankings are derived, when read, from the entries of the ranking in force (`ranking_service.get_ranking_in_force`). Nothing is copied per Socio and nothing is added to the HU-25 run, so the four rankings always come from the same run, rules version and calculation date, and the replacement is atomic by construction (HU-25 scenario 4). Rankings completed before this story are shown too.
- **Population**: only the Socios of that run, that is, Socios with fees up to date when it was calculated (HU-25). Fee status, `activo` and account activation are not re-checked; a Socio who left the roster or fell overdue afterwards stays in the tables until the next run, as in HU-36.
- **Name and membership number** come from the current roster, since the snapshot holds neither; the points, position and tiebreak come only from the stored entry and its snapshot.
- **Ordering uses the stored two-decimal components** (scoring model, rule 1), the same values HU-16 shows; differences beyond two decimals do not exist for ordering.
- **Saturated pillars**: Antigüedad y edad is bounded at `100·wT` and Participación institucional at `wP·Pinst_max`. When more than 10 Socios reach the bound, they are ordered by the same tiebreak as the general ranking (seniority, then age, then lower document number), like any other tie (scenario 6). For Antigüedad y edad that means the most senior Socios. The table shows no count of Socios sharing the maximum.
- **A pillar weighted 0** (for example `wP = 0`) gives 0.00 to every Socio: scenario 8 applies.
- **Formulas of the catalog**: the three pillars are those of `scoring-model`, today the only formula of the catalog. A future formula must declare in its descriptor which components form each pillar (scoring model, rule 9); until it does, its rankings show no pillar tables and the screen shows "La fórmula de este ranking no define rankings por pilar."
- **Rules published between runs**: the tables keep the rules version they were calculated with until the next run (as HU-16).
- **Multi-tenant**: the Admin only sees rankings of their own club (decision 34); the club is never taken from the request.
- **Privacy**: rows never include document number, email, address or distance. The document number is used for the tiebreak only, server side.
- **Read-only**: there is no operation to edit, hide or reorder a position; viewing the tables is not audited (as HU-30).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST offer, for the ranking in force, three rankings: Asistencia, Participación institucional and Antigüedad y edad.
- **FR-002**: System MUST take the Asistencia pillar as the sum of the stored components `attendance_frequency` and `attendance_distance`, and the other two pillars as `institutional` and `seniority_age`.
- **FR-003**: System MUST order each pillar by its stored points, descending, breaking ties by seniority, then age, then lower document number.
- **FR-004**: System MUST exclude the new-member bonus and the cap adjustment from every pillar.
- **FR-005**: System MUST derive the three rankings from the same `completed` run as the general ranking, never from a different run.
- **FR-006**: System MUST list at most 10 Socios per pillar, and only Socios with more than 0.00 points in it.
- **FR-007**: System MUST show, per row, position in the pillar, name, membership number and points with two decimals.
- **FR-008**: System MUST show the rules version and the completion time of the run.
- **FR-009**: System MUST show "Todavía no hay un ranking calculado." without a completed ranking, the empty-pillar message for a pillar with no points, and the "actualizando" label while a run is `running`.
- **FR-010**: System MUST restrict access to the Admin of the club, rejecting Socios and requests without a session.
- **FR-011**: System MUST NOT return document number, email, address or distance.

### Key Entities

- **PillarRanking** (derived, not stored): run, pillar (`attendance` / `institutional` / `seniority_age`), rules version, completed at, rows.
- **PillarRankingRow** (derived): position in the pillar, Socio, name, membership number, points.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For the control dataset, 100% of the pillar points shown equal the Socio's HU-16 breakdown.
- **SC-002**: The HU-25 run time does not change (the rankings add no work to the run).
- **SC-003**: 0 requests by a Socio or without a session obtain the pillar rankings.
- **SC-004**: 0 cases of pillar tables and general ranking coming from different runs.

## Assumptions

- The story does not change the formula or its weights; it reorders components HU-25 already stores.
- The three pillars are the three weighted terms of the scoring model (`wA·P_asistencia`, `wP·P_inst`, `wT·P_antigüedad`), named as in the HU-16 breakdown. Frequency and distance are separate in the breakdown but form a single pillar here, as they weigh together in the score.
- The top 10 is fixed: no pagination, no history of previous runs and no export in this story.
- Only the Admin sees the tables; publishing them to Socios is out of scope.
- Confirmed by the product owner (2026-11-19): the texts of scenario 8 and of a formula without pillars; saturated pillars use the general ranking tiebreak, with no count of tied Socios; no response-time target for this view (it reads one run and shows at most 30 rows).

## Revision Notes (v2)

- Translated to English and aligned with the format of the other specs; the folder was renamed from `hu-44-segmentation-ranking` (the story is not about wave segmentation).
- The rankings are derived from the stored entries instead of being persisted per run: atomicity and the shared run hold by construction, the HU-25 run time is unaffected and rankings calculated before this story are covered. The audit of "which pillar rankings each run produced" (old FR-17) is dropped: the run already records its rules version and nothing new is written.
- The overdue-fee scenario is restated as the HU-25 population (overdue Socios are never in the run).
- Added: two-decimal ordering, saturated pillars, a pillar weighted 0, other catalog formulas, name and number taken from the current roster, the first run still `running`, multi-tenancy and the 401 case.
- v3: the open questions are closed (decision 64): the empty-pillar and formula-without-pillars texts are confirmed, saturated pillars follow the general ranking tiebreak, and the 500,000-Socio response target (old SC-003) is dropped.

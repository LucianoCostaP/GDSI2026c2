# Feature Specification: Equity Analysis of a Rules Simulation

**Feature Branch**: `hu-30-equity-analysis`
**Created**: 2026-10-25 (v1)
**Status**: Draft
**Backlog Reference**: HU-30 (Estimate: 5, Priority: Media, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md)
**Input**: "As an Admin, I want to see how a change of weights affects the different Socio profiles, so that I detect whether a new rule harms or benefits a group disproportionately before applying it."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Equity Analysis of a Rules Simulation (Priority: P2)

**Why this priority**: The club must be able to defend its rules before its Socios; seeing which groups win or lose before applying a change is part of that.

**Independent Test**: Run a simulation (HU-29) that raises the distance weight and verify that, next to the general results, the distance segments show the expected changes in average score and position, and that the segment with the largest change is highlighted.

**Acceptance Scenarios**:

1. **Given** a simulation of HU-29, **When** its result is shown, **Then** the equity analysis is shown next to it on the same screen, computed from the same hypothetical values; it is not a separate simulation.
2. **Given** the analysis, **When** the Admin chooses an attribute, **Then** the Socios are segmented by it: seniority (years since alta, in bands), distance to the stadium (km, in bands) or age (years, in bands).
3. **Given** a segmentation, **When** it is shown, **Then** each segment shows its number of Socios and its average score and average position in the current ranking and in the simulated one, and the difference.
4. **Given** the segments, **When** they are shown, **Then** the segments whose change differs most from the rest (positive or negative) are highlighted, to make a possible bias visible.
5. **Given** a segment with fewer than 10 Socios, **When** it is shown, **Then** it is merged with its neighbor band, so no small group can be singled out.
6. **Given** the analysis, **When** it runs, **Then** no real score, position or rule changes.

---

### Edge Cases

- **Same data as HU-29**: the analysis uses the inputs snapshot of the latest completed ranking (scoring model rule 4), which stores T, E and the distance; it reads no other data.
- **Band limits**: fixed in the product (for example seniority 0–1, 1–5, 5–10, 10–20, 20+ years; distance 0–10, 10–50, 50–200, 200+ km; age 18–30, 30–45, 45–60, 60–75, 75+ years).
- **Socio type**: the backlog suggests segmenting by "tipo de socio", but the data contract has no such field. It can be added when the club sends it (HU-43).
- **Performance**: it shares the time target of HU-29 (cross-cutting section 6).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST compute the analysis over the same simulation as HU-29 and show it next to its general results.
- **FR-002**: System MUST segment Socios by seniority, distance and age bands.
- **FR-003**: System MUST show per segment the count, the average score and average position before and after, and the difference.
- **FR-004**: System MUST highlight the segments with the largest deviation.
- **FR-005**: System MUST merge segments with fewer than 10 Socios.
- **FR-006**: System MUST NOT modify any real data.

### Key Entities

- **EquitySegment**: attribute, band, number of Socios, average score and position before and after. Transient, part of the RulesSimulation of HU-29.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With hypothetical values identical to the ranking's rules, every segment shows a difference of 0.
- **SC-002**: The averages of the segments, weighted by their size, equal the overall averages of HU-29.

## Assumptions

- HU-42 (executive report, outside the MVP) reuses these segments.

# Feature Specification: Segment Socios into Waves

**Feature Branch**: `hu-36-wave-segmentation`
**Created**: 2026-10-11 | **Revised**: 2026-11-07 (v4)
**Status**: Draft
**Backlog Reference**: HU-36 (Estimate: 8, Priority: Alta, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md)
**Input**: "As an Admin, I want to automatically generate the segmentation of Socios into waves based on their ranking position, so that I establish the groups that will access turn reservation in a staggered way."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Segment Socios into Waves (Priority: P1)

As an Admin, I want to automatically generate the segmentation of Socios into waves based on their ranking position, so that I establish the groups that will access turn reservation in a staggered way.

**Why this priority**: Waves turn the ranking into actual priority.

**Independent Test**: For a published Partido and a completed ranking, trigger segmentation and verify five waves at 20%, 40%, 60%, 80% and 100%, with sizes differing by at most one Socio.

**Acceptance Scenarios**:

1. **Given** a `published` event of type Partido and a `completed` ranking, **When** the Admin triggers segmentation, **Then** the process starts for that event and records the ranking version it uses.
2. **Given** the process, **When** waves are defined, **Then** they are percentile bands of the ranking in steps of 20: wave 1 covers percentiles up to 20%, wave 2 up to 40%, wave 3 up to 60%, wave 4 up to 80% and wave 5 up to 100%. The step is a system setting (default 20).
3. **Given** a ranking of M Socios, **When** a Socio's position is p, **Then** their percentile is 100·p / M and they belong to wave k when (k − 1)·step < percentile ≤ k·step. Wave 1 holds the best positions.
4. **Given** the bands, **When** boundaries fall between positions, **Then** positions are assigned with whole numbers (the boundary of wave k is floor(k·step·M / 100)), so wave sizes differ by at most one Socio and the last wave ends at position M.
5. **Given** a generated segmentation, **When** it is shown, **Then** it includes, per wave, its order, the percentile range, the position range and the number of Socios.
6. **Given** an event that is not a published Partido, a Partido whose start has already passed, or no completed ranking with at least one ranked Socio, **When** the Admin triggers segmentation, **Then** it is not possible and the missing prerequisite is stated.
7. **Given** a segmentation already exists and the first wave has not opened, **When** the Admin generates it again, **Then** after confirmation it replaces the previous one and any existing schedule (HU-37) is invalidated.
8. **Given** the first wave already opened, **When** the Admin tries to generate again, **Then** it is blocked.
9. **Given** later ranking recalculations, **When** they complete, **Then** the generated waves do not change (the segmentation is fixed to its ranking version).
10. **Given** the latest successful roster load is older than the staleness limit (default 24 hours) at the time of generating, or there were successful loads (roster, attendance or activities) after the ranking that will be used, **When** the Admin starts the segmentation, **Then** they are warned before it runs and they can continue (HU-43 FR-008).

---

### Edge Cases

- **Only upcoming Partidos**: the event must be of type Partido and its start must not have passed. Institutional/amateur and historical events are not Partidos and are never segmented.
- **Who is segmented**: the Socios of the ranking version used, that is, Socios with fees up to date when that ranking was calculated. Fee status is not re-checked.
- **Small rankings**: a band that would hold no Socios is omitted, wherever it falls, and the remaining waves are renumbered 1 to N in order. Each wave keeps the percentile range of its original band. For example, with 3 Socios and step 20 the boundaries are 0, 1, 1, 2 and 3: bands 1 and 3 are empty, so there are three waves, wave 1 (20–40%, position 1), wave 2 (60–80%, position 2) and wave 3 (80–100%, position 3). HU-37 schedules these N waves.
- **Socios outside the ranking version** (joined or paid up afterwards) belong to no wave; HU-39 explains it.
- **Storage at scale**: the segmentation stores the ranking version, the step and the number of ranked Socios; each Socio's wave is derived from their position, so nothing is copied per Socio (up to 500,000).
- **Not in scope**: capacity of the stadium, Abonados and seat transfers.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let the Admin trigger segmentation for a published event of type Partido whose start has not passed, with a completed ranking.
- **FR-002**: System MUST define waves as percentile bands in steps of the configured step (default 20).
- **FR-003**: System MUST assign each ranked Socio to the wave that contains their percentile, with wave 1 holding the best positions.
- **FR-004**: System MUST use whole-number boundaries so that wave sizes differ by at most one Socio and every ranked Socio belongs to exactly one wave.
- **FR-005**: System MUST show, per wave, its order, percentile range, position range and number of Socios.
- **FR-006**: System MUST fix the segmentation to a ranking version.
- **FR-007**: System MUST allow regeneration only before the first wave opens, invalidating the schedule.
- **FR-008**: System MUST audit every generation.
- **FR-009**: System MUST warn, without blocking, when the roster is older than the staleness limit or when there were loads after the ranking that will be used.

### Key Entities

- **WaveSegmentation**: event, ranking version, number of ranked Socios, percentile step, generated at, generated by.
- **Wave**: order, percentile range, position range (derived), number of Socios.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of ranked Socios belong to exactly one wave.
- **SC-002**: Wave sizes differ by at most one Socio (a test with 103 Socios gives 20, 21, 20, 21, 21).
- **SC-003**: 0 waves change after a later ranking calculation.

## Assumptions

- Wave 1 is the best-ranked group ("percentile 20%" is the top 20% by position).
- The percentile step is configuration, not a screen.
- Waves apply to Partidos only; institutional/amateur events have no waves.

## Revision Notes (v3)

- Replaced the capacity-based rule with fixed percentile bands (20, 40, 60, 80, 100), as decided by the product owner.
- Wave membership is derived from the ranking version rather than stored per Socio.
- v4: only upcoming Partidos can be segmented; Partidos whose start has passed and historical events are rejected. Empty bands can fall in the middle: the remaining waves are renumbered 1 to N and keep their original percentile range. The ranking must have at least one ranked Socio. Added the staleness warning required by HU-43 FR-008, plus the warning for loads after the ranking.

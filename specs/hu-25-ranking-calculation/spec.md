# Feature Specification: Run Ranking Calculation

**Feature Branch**: `hu-25-ranking-calculation`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3)
**Status**: Draft
**Backlog Reference**: HU-25 (Estimate: 8, Priority: Alta, MVP: Yes). Re-estimate: the full scoring model with five components and a stored snapshot.
**Shared rules**: [scoring model](../_shared/scoring-model.md), [data contract](../_shared/data-contract.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an Admin, I want to run the Socios ranking calculation, so that the scoring reflects the attendance data and other variables loaded so far."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Ranking Calculation (Priority: P1)

As an Admin, I want to run the Socios ranking calculation, so that the scoring reflects the attendance data and other variables loaded so far.

**Why this priority**: The ranking is the core output: scores, positions, simulations and waves derive from it.

**Independent Test**: With attendance and participation loaded and rules in force, trigger the calculation, verify progress and completion messages, the stored components, the unique positions and the tiebreak.

**Acceptance Scenarios**:

1. **Given** an Admin logged in, **When** they trigger the calculation, **Then** the system takes a snapshot of the data and of the rules version in force and applies the scoring model (configured by the Admin, HU-28) to every Socio of the ranking population.
2. **Given** a calculation running, **When** the Admin looks at the screen, **Then** they are informed that the process is in progress, and a second run cannot be started.
3. **Given** the calculation finishes, **When** it succeeds, **Then** the Admin is told it completed and that the new ranking is in force since that moment.
4. **Given** a new ranking calculated, **When** it replaces the previous one, **Then** the replacement is atomic and the previous ranking remains in the history with its rules version.
5. **Given** the calculation fails, **When** the error occurs, **Then** the error is shown, the ranking is marked `failed` and the previous ranking stays in force unmodified.
6. **Given** two or more Socios with the same total score, **When** positions are assigned, **Then** ties are broken by greater seniority, then greater age, then lower document number.
7. **Given** the club data or the attendance data are older than the staleness limit, or a load happened after the last ranking, **When** the Admin starts the calculation, **Then** a warning is shown before the run and they can continue.
8. **Given** a completed ranking, **When** it is stored, **Then** each entry holds the five components, the cap adjustment, the total, the position and the inputs snapshot used by HU-16, HU-18 and HU-29.

---

### Edge Cases

- **Ranking population**: all Socios in the club data with fees up to date at the calculation time, whether or not their account is activated. Overdue Socios are left out but keep their history; once they pay up they return with their accumulated record (inside the windows).
- **Event types**: attendance at a Partido feeds the attendance pillar; attendance at an Evento institucional/amateur feeds the institutional pillar with the points defined for that event.
- **Volume**: up to 500,000 Socios (cross-cutting section 6).
- **Attendance window**: previous calendar year plus current year to date; counted events are those with a loaded attendance (scoring model).
- **Changes during a run** (weights, attendance) do not affect it; it uses its snapshot.
- **Failure atomicity**: a failed run MUST NOT leave a partially updated ranking.
- **Zero cases** follow the scoring model (no events, no attended matches).
- **Unique positions**: the full tiebreak makes positions unique because document numbers are unique.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let an Admin trigger the calculation manually and allow only one run at a time.
- **FR-002**: System MUST apply the scoring model with the rules version in force over attendance, participation, seniority, age, distance and bonus data.
- **FR-003**: System MUST inform that the process is running.
- **FR-004**: System MUST inform on completion and state since when the new ranking is in force (its completion time).
- **FR-005**: System MUST keep the previous rankings in a history, with the rules version used by each.
- **FR-006**: System MUST keep the previous ranking in force and show the error if the calculation fails.
- **FR-007**: System MUST break ties by seniority, then age, then lower document number.
- **FR-008**: System MUST use attendance of the previous year and the accumulated current year.
- **FR-009**: System MUST store components, total, position and the inputs snapshot per Socio, and the data versions used.
- **FR-010**: System MUST expose to Socios only `completed` rankings.
- **FR-011**: System MUST warn about stale data before starting.

### Key Entities

- **Ranking**: calculated at, completed at (in force since), rules version, population size, status (`running` / `completed` / `failed`), data versions used.
- **RankingEntry**: Socio, total, position, components, inputs snapshot.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of failed calculations leave the previous ranking unchanged.
- **SC-002**: 100% of completed rankings give every ranked Socio a unique position following the tiebreak.
- **SC-003**: Every completed ranking records its rules version and data versions.
- **SC-004**: A reference dataset reproduces the scoring-model worked example exactly (59.55).
- **SC-005**: The run completes under the time target in cross-cutting section 6.

## Assumptions

- Completion of the calculation is the confirmation: the new ranking replaces the old one at that moment (the backlog phrase "until the new one is confirmed" is read this way; confirmed by the product owner).
- Calculation is manual only.
- The calculation is deterministic: the same snapshot and rules always give the same ranking.

## Revision Notes (v2)

- Fixed the authority wording (weights are set by the Admin only).
- Added population, window, snapshot, single run, atomic replacement, staleness warning and the stored inputs.
- v3: eligibility and history rules confirmed; event types routed to their pillars; volume up to 500,000.

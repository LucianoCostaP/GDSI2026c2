# Feature Specification: Run Ranking Calculation

**Feature Branch**: `hu-25-ranking-calculation`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-25 (Estimate: 8, Priority: Alta, MVP: Yes)
**Input**: User description: "As a System Administrator, I want to run the Socios ranking calculation, so that the scoring reflects the attendance data and other variables loaded so far."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run Ranking Calculation (Priority: P1)

As a System Administrator, I want to run the Socios ranking calculation, so that the scoring reflects the attendance data and other variables loaded so far.

**Why this priority**: The ranking is the core product output: scores, positions, simulations and waves all derive from it.

**Independent Test**: With attendance loaded and rules in force, trigger the calculation, verify progress feedback and completion message, and verify ties follow the tiebreak order.

**Acceptance Scenarios**:

1. **Given** an Administrador logged in, **When** they trigger the ranking calculation manually, **Then** the system applies the scoring rules in force (set by the Dirigente or Administrador) over the available data (attendance, seniority and other configured variables).
2. **Given** a calculation running, **When** the Administrador looks at the screen, **Then** they are informed that the process is in progress.
3. **Given** the calculation finishes, **When** it succeeds, **Then** the Administrador is told it completed and since when the new ranking is in force.
4. **Given** a new ranking calculated, **When** it replaces the previous one, **Then** the previous ranking remains available in the history, preserving traceability.
5. **Given** the calculation fails, **When** the error occurs, **Then** the error is shown and the previous ranking is kept unmodified.
6. **Given** two or more Socios with the same score, **When** positions are assigned, **Then** ties are broken by seniority (greater wins), then by age (older wins), then by lower document number.

---

### Edge Cases

- **Attendance window**: attendance data reflects the previous year plus the accumulated current year.
- **Full tiebreak cascade**: seniority → age → lower document number, so positions are always unique.
- **Failure atomicity**: a failed run MUST NOT leave a partially updated ranking.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let an Administrador trigger the ranking calculation manually.
- **FR-002**: System MUST apply the scoring rules in force over attendance, seniority and other configured variables.
- **FR-003**: System MUST inform that the process is running.
- **FR-004**: System MUST inform on completion and state since when the new ranking is in force.
- **FR-005**: System MUST keep the previous ranking in the history so traceability is not lost.
- **FR-006**: System MUST keep the previous ranking unmodified and show the error if the calculation fails.
- **FR-007**: System MUST break ties by seniority (greater wins), then age (older wins), then lower document number.
- **FR-008**: System MUST use attendance data from the previous year and the accumulated current year.

### Key Entities

- **Ranking**: calculation version. Attributes: calculated at, in force since, rules version used, status (running / completed / failed).
- **RankingEntry**: Socio, total score, position, score components (see HU-16).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of failed calculations leave the previous ranking unchanged.
- **SC-002**: 100% of completed rankings give every Socio a unique position following the tiebreak order.
- **SC-003**: Every completed ranking records which rules version it applied.

## Assumptions

- Completion of the calculation is treated as the confirmation after which the new ranking replaces the old one; if the backlog intends a separate confirmation step it must be clarified (see README).
- Calculation is manual only; scheduled runs are not in scope.

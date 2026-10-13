# Feature Specification: Estimated Score Simulator by Attendance

**Feature Branch**: `hu-18-attendance-score-simulator`
**Created**: 2026-10-11 | **Revised**: 2026-10-12 (v2)
**Status**: Draft
**Backlog Reference**: HU-18 (Estimate: 8, Priority: Media, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Socio of the club, I want to simulate how attending or not attending the next event would affect my score, so that I can anticipate the impact of my decision on my total score."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Estimated Score Simulator by Attendance (Priority: P2)

As a Socio of the club, I want to simulate how attending or not attending the next event would affect my score, so that I can anticipate the impact of my decision on my total score.

**Why this priority**: Makes the effect of the scoring rules tangible and encourages attendance.

**Independent Test**: As a Socio, pick an upcoming event and verify the projected score if attending and if not attending, that attending raises or keeps it and not attending never raises it, and that the real score is unchanged.

**Acceptance Scenarios**:

1. **Given** a logged-in Socio in the latest completed ranking and available upcoming events, **When** they select one event, **Then** the simulation for that event starts.
2. **Given** a selected event, **When** the simulation runs, **Then** the system shows the projected total if the Socio attended: the event is added to both the attended and the total counts with its class factor C(I), and the distance term is recomputed, under the rules version of the latest ranking.
3. **Given** the same simulation, **When** it runs, **Then** the system shows the projected total if the Socio did not attend: the event is added only to the total count, so the frequency term falls.
4. **Given** any simulation, **When** it completes, **Then** the current total, both projections and the difference with the current total are shown, each capped at 100, and the Socio's real score is not modified.
5. **Given** a Socio not in the latest completed ranking, **When** they open the simulator, **Then** an informative message explains that a simulation needs a calculated score.
6. **Given** the rules in force differ from those of the latest ranking, **When** the simulation is shown, **Then** it states which rules version it used.

---

### Edge Cases

- **No upcoming events**: same empty state as HU-17.
- **Repeat simulations** never accumulate effects.
- **Event not in the denominator**: upcoming events are not part of the current score (only events with loaded attendance count), so the current total is the baseline.
- **Position**: projecting the new position is out of the MVP. [NEEDS CLARIFICATION: the feature map mentions "posiciones que escalaría"; confirm if wanted.]

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let the Socio select an upcoming published event to simulate.
- **FR-002**: System MUST calculate the projected total if attending, using the stored inputs snapshot and the scoring model.
- **FR-003**: System MUST calculate the projected total if not attending.
- **FR-004**: System MUST NOT modify the Socio's real score or any stored data.
- **FR-005**: System MUST show the rules version used and cap results at 100.

### Key Entities

- **AttendanceSimulation**: Socio, event, current score, projected score attending, projected score not attending, rules version. Transient.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of simulations leave the real score and stored data unchanged.
- **SC-002**: Simulated results equal what the official calculation would give if the Socio attended or not, in a parity test with the same inputs.

## Assumptions

- Uses the inputs snapshot stored by HU-25 (class-weighted sums, distance terms), so no source data is re-read.
- The simulation assumes the rest of the Socio's data does not change.

## Revision Notes (v2)

- "Not attending" is now defined by the formula (denominator grows, numerator does not).
- Anchored to the rules version of the latest ranking and added the parity test.

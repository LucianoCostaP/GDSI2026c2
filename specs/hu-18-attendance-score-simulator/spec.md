# Feature Specification: Estimated Score Simulator by Attendance

**Feature Branch**: `hu-18-attendance-score-simulator`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-18 (Estimate: 8, Priority: Media, MVP: Yes)
**Input**: User description: "As a Socio of the club, I want to simulate how attending or not attending the next event would affect my score, so that I can anticipate the impact of my decision on my total score."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Estimated Score Simulator by Attendance (Priority: P2)

As a Socio of the club, I want to simulate how attending or not attending the next event would affect my score, so that I can anticipate the impact of my decision on my total score.

**Why this priority**: Helps Socios make informed attendance decisions and makes the effect of the scoring rules tangible.

**Independent Test**: As a Socio, pick an upcoming event and verify the system shows the resulting score if attending and if not attending, and that the real score stays unchanged.

**Acceptance Scenarios**:

1. **Given** a logged-in Socio and available upcoming events, **When** they select one event to simulate, **Then** the simulation for that event is started.
2. **Given** a selected event, **When** the simulation runs, **Then** the system shows how many points would be added to the Socio's current score if they attended, per the scoring rules in force.
3. **Given** the same simulation, **When** it runs, **Then** the system also shows how the score would be affected if the Socio did not attend.
4. **Given** any simulation, **When** it completes, **Then** the Socio's real score is not modified.

---

### Edge Cases

- **No upcoming events**: nothing can be simulated; the Socio is informed (same empty state as HU-17).
- **Repeat simulations**: running several simulations never accumulates effects on the real score.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let the Socio select an upcoming available event to simulate.
- **FR-002**: System MUST calculate and show the points that attending would add, using the scoring rules in force.
- **FR-003**: System MUST calculate and show the effect on the score of not attending.
- **FR-004**: System MUST NOT modify the Socio's real score as a result of a simulation.

### Key Entities

- **AttendanceSimulation**: Socio, event, current score, projected score if attending, projected score if not attending. Transient result, not part of the real score.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of simulations leave the real score unchanged.
- **SC-002**: Simulated results follow the scoring rules in force at the time of simulation.

## Assumptions

- The scoring rules in force are those configured via HU-28; events come from HU-17.

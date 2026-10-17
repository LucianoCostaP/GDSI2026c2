# Feature Specification: Estimated Score Simulator by Attendance

**Feature Branch**: `hu-18-attendance-score-simulator`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3)
**Status**: Draft
**Backlog Reference**: HU-18 (Estimate: 8, Priority: Media, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Member of the club, I want to simulate how attending or not attending the next event would affect my score, so that I can anticipate the impact of my decision on my total score."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Estimated Score Simulator by Attendance (Priority: P2)

As a Member of the club, I want to simulate how attending or not attending the next event would affect my score, so that I can anticipate the impact of my decision on my total score.

**Why this priority**: Makes the effect of the scoring rules tangible and encourages attendance.

**Independent Test**: As a Member, pick an upcoming event and verify the projected score if attending and if not attending, that attending raises or keeps it and not attending never raises it, and that the real score is unchanged.

**Acceptance Scenarios**:

1. **Given** a logged-in Member in the latest completed ranking and available upcoming events, **When** they select one event, **Then** the simulation for that event starts.
2. **Given** a selected event of type **Partido**, **When** the simulation runs, **Then** the system shows the projected total if the Member attended: the event is added to both the attended and the total counts with its class factor C(I), and the distance term is recomputed, under the rules version of the latest ranking.
3. **Given** the same Partido, **When** it runs, **Then** the system shows the projected total if the Member did not attend: the event is added only to the total count, so the frequency term falls.
4. **Given** a selected event of type **Evento institucional/amateur**, **When** the simulation runs, **Then** attending adds the points defined for that event at its publication to the participation pillar (respecting its cap) and not attending leaves the score unchanged.
5. **Given** any simulation, **When** it completes, **Then** the current total, both projections and the difference with the current total are shown, each capped at 100, and the Member's real score is not modified.
6. **Given** a Member not in the latest completed ranking, **When** they open the simulator, **Then** an informative message explains that a simulation needs a calculated score.
7. **Given** the rules in force differ from those of the latest ranking, **When** the simulation is shown, **Then** it states which rules version it used.
8. **Given** a simulation result, **When** it is shown, **Then** it also includes an **estimated position** for each projection, obtained by placing the projected score among the current scores of the other Members in the latest ranking. It is labeled "estimación: supone que los demás socios no cambian" and states that it can differ after the next calculation.

---

### Edge Cases

- **No upcoming events**: same empty state as HU-17.
- **Repeat simulations** never accumulate effects.
- **Event not in the denominator**: upcoming events are not part of the current score (only events with loaded attendance count), so the current total is the baseline.
- **Estimated position**: equals 1 plus the number of Members whose current total is strictly higher. When Members share the projected score, the position is shown as approximate. It is an estimate only, because the behavior of the other Members is unknowable and the new event also moves their scores (it enters everyone's denominator).
- **Estimated position is secondary**: if it cannot be computed, the score projections are still shown.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let the Member select an upcoming published event to simulate.
- **FR-002**: System MUST calculate the projected total if attending, using the stored inputs snapshot and the scoring model, for both event types.
- **FR-003**: System MUST calculate the projected total if not attending.
- **FR-004**: System MUST NOT modify the Member's real score or any stored data.
- **FR-005**: System MUST show the rules version used and cap results at 100.
- **FR-006**: System MUST show an estimated position per projection, clearly labeled as an estimate that holds the other Members constant.

### Key Entities

- **AttendanceSimulation**: Member, event, current score, projected score attending, projected score not attending, estimated positions, rules version. Transient.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of simulations leave the real score and stored data unchanged.
- **SC-002**: Simulated results equal what the official calculation would give if the Member attended or not, in a parity test with the same inputs.
- **SC-003**: 100% of estimated positions carry the estimate label.

## Assumptions

- Uses the inputs snapshot stored by HU-25 (class-weighted sums, distance terms, participation points), so no source data is re-read.
- The simulation assumes the rest of the Member's data does not change.
- Decided by the product owner: the position cannot be known exactly, but an estimate is welcome when it can be computed.

## Revision Notes (v3)

- Added the estimated position (labeled), support for institutional/amateur events and the type-specific behavior.
- Removed the open question about projecting the position.

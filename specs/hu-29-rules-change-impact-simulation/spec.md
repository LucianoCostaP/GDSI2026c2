# Feature Specification: Simulate Impact of a Rules Change

**Feature Branch**: `hu-29-rules-change-impact-simulation`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-29 (Estimate: 8, Priority: Media, MVP: Yes)
**Input**: User description: "As a Dirigente or Administrador, I want to simulate the impact of a change in weights before applying it, so that I can anticipate how the ranking would be redistributed without affecting the real scoring of Socios."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Simulate Impact of a Rules Change (Priority: P2)

As a Dirigente or Administrador, I want to simulate the impact of a change in weights before applying it, so that I can anticipate how the ranking would be redistributed without affecting the real scoring of Socios.

**Why this priority**: Lets decision makers preview consequences of a rule change and avoid unwanted effects on the real ranking.

**Independent Test**: Enter hypothetical weights and verify the side-by-side comparison with the current situation, histogram, mean, median, and the counts of Socios moving up and down, with the real ranking unchanged.

**Acceptance Scenarios**:

1. **Given** a Dirigente or Administrador logged in, **When** they enter hypothetical weights different from those in force, **Then** the system accepts them as simulation input.
2. **Given** simulation input, **When** the simulation runs, **Then** the result is calculated over current data without modifying the real ranking.
3. **Given** a simulation result, **When** it is shown, **Then** it includes a histogram of the resulting score distribution plus mean and median.
4. **Given** a simulation result, **When** it is shown, **Then** it includes how many Socios would go up and how many would go down in position versus the current ranking.
5. **Given** any result, **When** it is shown, **Then** it is always side by side with the current situation (before/after), never in isolation.
6. **Given** the simulation, **When** it runs, **Then** it does not require the real adjustment flow (HU-28) nor the official calculation (HU-25).
7. **Given** a finished simulation, **When** the user changes the values, **Then** it can be repeated with different values as many times as wanted before deciding to apply a real change.

---

### Edge Cases

- **No effect on real data**: scores, positions and rules in force never change as a result of a simulation.
- **Unchanged Socios**: Socios whose position does not change count in neither "up" nor "down".
- **Weights outside allowed limits**: treated as in HU-28 (to confirm).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept hypothetical weights different from those in force.
- **FR-002**: System MUST compute the simulated result over current data without modifying the real ranking.
- **FR-003**: System MUST show a score distribution histogram with mean and median.
- **FR-004**: System MUST show the number of Socios moving up and moving down versus the current ranking.
- **FR-005**: System MUST always show simulated results side by side with the current situation.
- **FR-006**: System MUST NOT require HU-28 or HU-25 to run a simulation.
- **FR-007**: System MUST allow unlimited repetition with different values.

### Key Entities

- **RulesSimulation**: hypothetical weights, simulated scores and positions, comparison against current ranking. Not persisted as real data.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 real scores or positions change as a result of any simulation.
- **SC-002**: 100% of simulation results are shown next to the current situation.

## Assumptions

- Simulation runs over the data of the latest completed ranking (HU-25); with no ranking yet there is no baseline to compare against.

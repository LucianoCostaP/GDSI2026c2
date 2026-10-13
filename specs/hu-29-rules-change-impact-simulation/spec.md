# Feature Specification: Simulate Impact of a Rules Change

**Feature Branch**: `hu-29-rules-change-impact-simulation`
**Created**: 2026-10-11 | **Revised**: 2026-10-12 (v2)
**Status**: Draft
**Backlog Reference**: HU-29 (Estimate: 8, Priority: Media, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Dirigente or Administrador, I want to simulate the impact of a change in weights before applying it, so that I can anticipate how the ranking would be redistributed without affecting the real scoring of Socios."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Simulate Impact of a Rules Change (Priority: P2)

As a Dirigente or Administrador, I want to simulate the impact of a change in parameters before applying it, so that I can anticipate how the ranking would be redistributed without affecting the real scoring of Socios.

**Why this priority**: Lets decision makers preview consequences of a rule change.

**Independent Test**: Enter hypothetical values and verify the side-by-side comparison with the current ranking, the histogram, mean and median, and the counts of Socios moving up and down, with the real ranking unchanged.

**Acceptance Scenarios**:

1. **Given** a Dirigente or Administrador logged in and a completed ranking, **When** they open the simulator, **Then** the inputs are pre-filled with the rules version of that ranking and any parameter of the scoring model can be changed.
2. **Given** hypothetical values, **When** they are outside the limits or the pillar weights do not add up to 1.00, **Then** the simulation is blocked with the same messages as HU-28.
3. **Given** valid hypothetical values, **When** the simulation runs, **Then** every Socio is recomputed from the stored inputs snapshot of the latest completed ranking, applying the scoring model and the tiebreak, without modifying any real data.
4. **Given** a simulation result, **When** it is shown, **Then** it includes a histogram of the score distribution in fixed bins of 5 points (0–100), with mean and median.
5. **Given** a simulation result, **When** it is shown, **Then** it includes how many Socios would go up and how many would go down in position versus the current ranking.
6. **Given** any result, **When** it is shown, **Then** it is side by side with the current situation (before/after), including the rules version of each side.
7. **Given** the simulation, **When** it runs, **Then** it does not require the real adjustment flow (HU-28) nor a new official calculation (HU-25).
8. **Given** a finished simulation, **When** the user changes the values, **Then** it can be repeated as many times as wanted.
9. **Given** hypothetical values identical to the ranking's rules, **When** it runs, **Then** 0 Socios go up, 0 go down and the distributions are equal.
10. **Given** no completed ranking exists, **When** the user opens the simulator, **Then** an informative message explains that there is no baseline.

---

### Edge Cases

- **No effect on real data**: scores, positions and rules in force never change.
- **Unchanged Socios** count in neither "up" nor "down".
- **Scope**: the simulation covers only the Socios and data in the latest completed ranking; later changes in data are not reflected until HU-25 runs.
- **Dirigente and Administrador** have the same access. Nothing is persisted.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept hypothetical values for any parameter of the scoring model.
- **FR-002**: System MUST validate them with the same limits and sum rule as HU-28.
- **FR-003**: System MUST compute the simulated result from the stored snapshot without modifying the real ranking.
- **FR-004**: System MUST show a histogram (5-point bins), mean and median, for both situations.
- **FR-005**: System MUST show the number of Socios moving up and down versus the current ranking.
- **FR-006**: System MUST always show results side by side with the current situation.
- **FR-007**: System MUST NOT require HU-28 or HU-25 to run a simulation.
- **FR-008**: System MUST allow unlimited repetition.
- **FR-009**: System MUST return the result within the target in cross-cutting section 6.

### Key Entities

- **RulesSimulation**: hypothetical parameter values, simulated scores and positions, comparison with the current ranking. Transient.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 real scores, positions or rules change as a result of any simulation.
- **SC-002**: 100% of results are shown next to the current situation.
- **SC-003**: Parity test: applying the simulated values in HU-28 and running HU-25 on the same data gives exactly the simulated scores and positions.
- **SC-004**: 95% of simulations return within 3 seconds for the expected volume.

## Assumptions

- Baseline ("before") is the stored latest completed ranking, computed with its own rules version, which may differ from the rules in force; both are displayed.
- Decided: all matrix parameters can be simulated because the inputs snapshot contains raw values, not only pillar scores.

## Revision Notes (v2)

- Defined baseline, histogram bins, tiebreak in simulated positions, validation, parity test and performance target.

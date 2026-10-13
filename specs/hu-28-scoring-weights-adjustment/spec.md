# Feature Specification: Adjust Scoring Parameters

**Feature Branch**: `hu-28-scoring-weights-adjustment`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3)
**Status**: Draft
**Backlog Reference**: HU-28 (Estimate: 5, Priority: Media, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Dirigente of the club, I want to adjust the weights of the variables in the base scoring formula, so that I define which Socio behaviors are prioritized when the ranking is calculated."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Adjust Scoring Parameters (Priority: P2)

As a Dirigente of the club, I want to adjust the weights of the variables in the base scoring formula, so that I define which Socio behaviors are prioritized when the ranking is calculated.

**Why this priority**: Lets the club decide its priorities without changing the algorithm structure.

**Independent Test**: As a Dirigente, change one weight, confirm the warning, and verify the new rules version is in force immediately, logged in the history, and the ranking unchanged until HU-25 runs.

**Acceptance Scenarios**:

1. **Given** a Dirigente logged in, **When** they open the scoring configuration, **Then** they see all parameters of the scoring model (section 4 of the model) with their current values, allowed limits and the rules version.
2. **Given** the parameter list, **When** the Dirigente edits a value, **Then** they can change each parameter within its limits and cannot add or remove parameters or change the formula structure or the constants.
3. **Given** edited pillar weights, **When** they do not add up to 1.00, **Then** saving is blocked and the sum is shown.
4. **Given** a changed `dsat`, **When** it is shown, **Then** the derived `b` is displayed read-only and the curve is described as having its inflection at `dsat`.
5. **Given** a value outside its limits, **When** saving, **Then** it is rejected with a message naming the parameter and its limits.
6. **Given** changed values, **When** the Dirigente tries to save, **Then** a confirmation message states these values will become the official rules in force.
7. **Given** the Dirigente confirms, **When** the save completes, **Then** a new rules version is in force immediately, with no extra approval or publication step.
8. **Given** new rules in force, **When** the ranking is viewed, **Then** it is unchanged until the calculation (HU-25) is run, and the Socio screens show the notice defined in HU-13.
9. **Given** a change, **When** it is saved, **Then** the rules version history records who, when, and previous and new values.
10. **Given** the current time is within 14 days before the season start (or after it), **When** the Dirigente tries to change values, **Then** the change is rejected with the cut-off date.
11. **Given** two Dirigentes editing at once, **When** the second saves from an outdated version, **Then** the save is refused and they must reload.

---

### Edge Cases

- **Season cut-off**: changes are allowed only until 14 days before the season start (Buenos Aires time). The window reopens when the next season start date is configured.
- **First version**: rules version 1 is seeded with the model defaults.
- **No effect on the ranking** until HU-25 runs.
- **Administrador**: cannot edit parameters (read-only access is out of scope).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list every parameter of the scoring model with its current value and limits.
- **FR-002**: System MUST allow changing each parameter within its limits.
- **FR-003**: System MUST NOT allow changing the formula structure, constants or the set of parameters.
- **FR-004**: System MUST require `wA + wP + wT = 1.00`.
- **FR-005**: System MUST ask for confirmation, stating these values become the official rules, before saving.
- **FR-006**: System MUST put confirmed values in force immediately as a new rules version.
- **FR-007**: System MUST NOT change the ranking until the calculation (HU-25) is run.
- **FR-008**: System MUST record every change in the rules version history (who, when, previous and new values).
- **FR-009**: System MUST reject changes later than 14 days before the season start.
- **FR-010**: System MUST prevent concurrent overwrites (version check).

### Key Entities

- **ScoringParameter**: name, symbol, current value, limits.
- **RulesVersion**: values per parameter, in force since, author, previous version, number.
- **Season** (setting): start date.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of confirmed changes are in force immediately and appear in the history with author and values.
- **SC-002**: 0 changes are accepted after the season cut-off or outside the limits.
- **SC-003**: 0 ranking changes happen without running HU-25.
- **SC-004**: 0 saved versions have pillar weights that do not add up to 1.00.

## Assumptions

- The base formula is the scoring model in `scoring-model.md`, delivered pre-defined (HU-27 is outside the MVP). The limits in that file were confirmed by the club.
- The season start date is a system setting seeded by the team; there is no screen for it in the MVP.
- Tests inject the current date to exercise the cut-off.

## Revision Notes (v2)

- The "variables and weights" are now the full parameter matrix; added limits, sum rule, derived `b`, concurrency and season-window semantics.
- v3: limits confirmed by the club.

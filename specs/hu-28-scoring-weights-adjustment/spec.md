# Feature Specification: Adjust Scoring Weights

**Feature Branch**: `hu-28-scoring-weights-adjustment`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-28 (Estimate: 5, Priority: Media, MVP: Yes)
**Input**: User description: "As a Dirigente of the club, I want to adjust the weights of the variables in the base scoring formula, so that I define which Socio behaviors are prioritized when the ranking is calculated."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Adjust Scoring Weights (Priority: P2)

As a Dirigente of the club, I want to adjust the weights of the variables in the base scoring formula, so that I define which Socio behaviors are prioritized when the ranking is calculated.

**Why this priority**: Lets the club decide its priorities without changing the algorithm structure.

**Independent Test**: As a Dirigente, change one weight, confirm the warning and verify the new version is in force immediately, logged in the history, and the ranking is unchanged until HU-25 runs.

**Acceptance Scenarios**:

1. **Given** a Dirigente logged in, **When** they open the scoring configuration, **Then** they see the variables of the published base formula with their current weights.
2. **Given** the variables list, **When** the Dirigente edits a weight, **Then** they can change each weight within the limits the base formula allows and cannot add or remove variables.
3. **Given** changed weights, **When** the Dirigente tries to save, **Then** a confirmation message states these weights will become the official rules in force.
4. **Given** the Dirigente confirms, **When** the save completes, **Then** the new weights are in force immediately, with no extra approval or separate publication step.
5. **Given** new weights in force, **When** the ranking is viewed, **Then** it is unchanged until the calculation (HU-25) is run.
6. **Given** a weights change, **When** it is saved, **Then** the rules version history records who, when, and previous and new values.
7. **Given** fewer than 2 weeks remain before the season starts, **When** the Dirigente tries to change weights, **Then** the change is rejected.

---

### Edge Cases

- **Out-of-limits value**: a weight outside the permitted limits is rejected with a message.
- **Season cut-off**: weights can only be changed up to 2 weeks before the start of the season.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list the base formula variables, published by the Administrador, with their current weights.
- **FR-002**: System MUST allow changing each variable's weight within the limits the base formula permits.
- **FR-003**: System MUST NOT allow adding or removing variables.
- **FR-004**: System MUST ask for confirmation, stating these weights become the official rules, before saving.
- **FR-005**: System MUST put confirmed weights in force immediately, with no additional approval or publication step.
- **FR-006**: System MUST NOT change the ranking until the calculation (HU-25) is run.
- **FR-007**: System MUST record every change in the rules version history (who, when, previous and new values).
- **FR-008**: System MUST reject weight changes later than 2 weeks before the start of the season.

### Key Entities

- **ScoringVariable**: name, current weight, allowed limits.
- **RulesVersion**: weight configuration in force. Attributes: values per variable, in force since, author, previous version.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of confirmed changes are in force immediately and appear in the version history with author and values.
- **SC-002**: 0 changes are accepted after the season cut-off.
- **SC-003**: 0 ranking changes happen without running HU-25.

## Assumptions

- The base formula (HU-27) is not in the MVP; it is assumed pre-defined with its variables and limits.
- The season start date is a known system value (source not defined in the backlog).

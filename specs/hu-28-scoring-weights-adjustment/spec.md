# Feature Specification: Adjust Scoring Parameters

**Feature Branch**: `hu-28-scoring-weights-adjustment`
**Created**: 2026-10-11 | **Revised**: 2026-10-26 (v4)
**Status**: Draft
**Backlog Reference**: HU-28 (Estimate: 5, Priority: Media, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an Admin of the club, I want to adjust the parameters defined by the scoring model within their limits, so that I define which Socio behaviors are prioritized when the ranking is calculated."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Adjust Scoring Parameters (Priority: P2)

As an Admin of the club, I want to adjust the weights of the variables in the base scoring formula, so that I define which Socio behaviors are prioritized when the ranking is calculated.

**Why this priority**: Lets the club decide its priorities without changing the algorithm structure.

**Independent Test**: As an Admin, change one weight, confirm the warning, and verify the new rules version is in force immediately, audited, and the ranking unchanged until HU-25 runs.

**Acceptance Scenarios**:

1. **Given** an Admin logged in, **When** they open the scoring configuration, **Then** they see all parameters of the formula in force (for the scoring model v1, section 4 of the model) with their current values, allowed limits and the rules version.
2. **Given** the parameter list, **When** the Admin edits a value, **Then** they can change each parameter within its limits and cannot add or remove parameters or change the formula structure or the constants.
3. **Given** edited pillar weights, **When** they do not add up to 1.00, **Then** saving is blocked and the sum is shown.
4. **Given** a changed `dsat`, **When** it is shown, **Then** the derived values of the formula (for the scoring model v1, `b`) are displayed read-only and the curve is described as having its inflection at `dsat`.
5. **Given** a value outside its limits, **When** saving, **Then** it is rejected with a message naming the parameter and its limits.
6. **Given** changed values, **When** the Admin tries to save, **Then** a confirmation message states these values will become the official rules in force.
7. **Given** the Admin confirms, **When** the save completes, **Then** a new rules version is in force immediately, with no extra approval or publication step.
8. **Given** new rules in force, **When** the ranking is viewed, **Then** it is unchanged until the calculation (HU-25) is run, and the Socio screens show the notice defined in HU-13.
9. **Given** a change, **When** it is saved, **Then** the audit records who, when, and previous and new values. There is no version history screen in the MVP.
10. **Given** the current time is within 14 days before the season start (or after it), **When** the Admin tries to change values, **Then** the change is rejected with the cut-off date.
11. **Given** two Admins editing at once, **When** the second saves from an outdated version, **Then** the save is refused and they must reload.
12. **Given** the club has no published formula (HU-27) or the formula is locked (HU-27, scenario 11), **When** an Admin tries to change values, **Then** the change is rejected with the reason; the lock is independent from the season cut-off and both must allow the change.

---

### Edge Cases

- **Season cut-off**: changes are allowed only until 14 days before the season start (Buenos Aires time). The window reopens when the next season start date is configured.
- **First version**: rules version 1 is not seeded: the Admin creates it when publishing the base formula (HU-27). HU-28 creates the following versions of the formula in force.
- **Per club**: rules versions and lock belong to the club of the Admin; the club is taken from the account.
- **No effect on the ranking** until HU-25 runs.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list every parameter of the scoring model with its current value and limits.
- **FR-002**: System MUST allow changing each parameter within its limits.
- **FR-003**: System MUST NOT allow changing the formula structure, constants or the set of parameters.
- **FR-004**: System MUST require `wA + wP + wT = 1.00`.
- **FR-005**: System MUST ask for confirmation, stating these values become the official rules, before saving.
- **FR-006**: System MUST put confirmed values in force immediately as a new rules version.
- **FR-007**: System MUST NOT change the ranking until the calculation (HU-25) is run.
- **FR-008**: System MUST audit every change (who, when, previous and new values) and store each rules version unchanged; a history view is outside the MVP.
- **FR-009**: System MUST reject changes later than 14 days before the season start.
- **FR-010**: System MUST prevent concurrent overwrites (version check).
- **FR-011**: System MUST reject changes while the formula is locked or when no formula is published (HU-27).
- **FR-012**: System MUST validate with decimal arithmetic and the same code as HU-27, and keep versions per club.

### Key Entities

- **ScoringParameter**: name, symbol, current value, limits.
- **RulesVersion**: values per parameter, in force since, author, previous version, number.
- **Season** (setting): start date.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of confirmed changes are in force immediately and appear in the audit with author and values.
- **SC-002**: 0 changes are accepted after the season cut-off or outside the limits.
- **SC-003**: 0 ranking changes happen without running HU-25.
- **SC-004**: 0 saved versions have pillar weights that do not add up to 1.00.

## Assumptions

- The base formula is a formula of the catalog (the scoring model in `scoring-model.md` in the MVP), published by the Admin (HU-27); this story adjusts the parameters of the formula in force and needs a published, unlocked formula. The limits in that file were confirmed by the club.
- The season start date is a system setting seeded by the team; there is no screen for it in the MVP.
- Tests inject the current date to exercise the cut-off.

## Revision Notes (v2)

- The "variables and weights" are now the full parameter matrix; added limits, sum rule, derived `b`, concurrency and season-window semantics.
- v3: limits confirmed by the club.
- v4: rules version 1 comes from HU-27 (not seeded); added the lock, per-club versions and decimal validation.

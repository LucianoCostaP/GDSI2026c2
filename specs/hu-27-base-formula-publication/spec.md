# Feature Specification: Publish the Base Scoring Formula

**Feature Branch**: `hu-27-base-formula-publication`
**Created**: 2026-10-25 (v1)
**Status**: Draft
**Backlog Reference**: HU-27 (Estimate: 2, Priority: Media, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an Admin, I want to publish the base formula of the scoring system, with its variables and configurable weights, so that the weights can later be adjusted (HU-28) without changing the structure of the algorithm."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Publish the Base Scoring Formula (Priority: P2)

**Why this priority**: Without a published base formula there are no rules in force: HU-28 cannot adjust parameters and HU-25 cannot calculate a ranking.

**Independent Test**: On a fresh system, verify HU-25 and HU-28 are blocked. As an Admin, open the base formula, review its variables, set initial weights within the limits and publish. Verify that rules version 1 is in force, that HU-28 shows it, and that variables cannot be added or removed.

**Acceptance Scenarios**:

1. **Given** no published base formula, **When** the Admin opens it, **Then** they see its structure: the variables of the scoring model (attendance frequency, distance, institutional participation, seniority and age, new-member bonus) and every parameter of section 4 with its default and limits, prefilled with the defaults.
2. **Given** the base formula, **When** the Admin sets the initial weights and parameters, **Then** they are validated with the limits and the sum rule of HU-28.
3. **Given** valid values, **When** the Admin confirms the publication, **Then** the base formula is published, its values become rules version 1 in force, and HU-28 can adjust them from then on.
4. **Given** a published base formula, **When** an Admin adjusts it (HU-28), **Then** they can change only the weights and parameters, never add or remove variables or change the structure.
5. **Given** a new version of the base formula (for example one that adds a variable), **When** it is shipped with the product and the Admin publishes it, **Then** it is recorded in the version history with who and when, and a new rules version starts from it.
6. **Given** no published base formula, **When** an Admin tries to adjust parameters (HU-28) or calculate the ranking (HU-25), **Then** the action is blocked with the reason.
7. **Given** a logged-in Socio, **When** they look for this action, **Then** it is not available and the server rejects the request.

---

### Edge Cases

- **One scoring implementation**: the variables and the formula are defined in code (`scoring-model.md`); the Admin publishes them, but cannot create a variable from the screen. Changing the structure means shipping a new version of the model.
- **Publishing again** the same base formula version is not possible; the next change of values goes through HU-28.
- **Audit**: every publication records who, when and the values.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST show the structure of the base formula with its variables, parameters, defaults and limits.
- **FR-002**: System MUST validate the initial values with the same rules as HU-28.
- **FR-003**: System MUST create rules version 1 in force when the base formula is published.
- **FR-004**: System MUST NOT allow adding or removing variables from the screen.
- **FR-005**: System MUST record every published base formula version in the version history.
- **FR-006**: System MUST block HU-25 and HU-28 until a base formula is published.
- **FR-007**: System MUST restrict this action to Admins, enforced on the server, and audit it.

### Key Entities

- **BaseFormulaVersion**: number, variables, parameters with limits, published at, published by.
- **RulesVersion**: as in HU-28, plus the base formula version it belongs to.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 rankings are calculated without a published base formula.
- **SC-002**: 100% of publications appear in the version history with author and values.

## Assumptions

- The product ships the scoring model v1 as the only base formula version of the MVP; "a new variable" (scenario 5) requires a new release.
- This replaces the earlier bootstrap task "seed rules version 1": the defaults are shipped, and the Admin publishes them.

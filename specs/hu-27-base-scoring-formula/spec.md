# Feature Specification: Publish the Base Scoring Formula

**Feature Branch**: `hu-27-base-scoring-formula`  
**Created**: 2026-10-17  
**Status**: Draft  
**Backlog Reference**: HU-27 (Estimate: 2, Priority: Media, MVP: Yes)  
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)  
**Input**: "As a System Administrator, I want to publish the base scoring formula, its variables and initial weights, so that the Dirigente can later adjust weights without changing the algorithm structure."

## User Scenarios & Testing

### User Story 1 - Publish a Formula Version (Priority: P2)

As a System Administrator, I want to publish a version of the base scoring formula so the club can use a controlled formula structure and a Dirigente can configure its permitted parameters.

**Why this priority**: The ranking and configuration stories need a defined, versioned formula as their foundation.

**Independent Test**: As an Administrador, review the seeded formula, publish its initial version, and verify HU-28 can read its parameter set while a Socio ranking calculation can refer to the formula version used.

**Acceptance Scenarios**:

1. **Given** the Administrador opens formula configuration, **When** the current formula is displayed, **Then** the system shows its variables, formula structure, constants, initial values and version.
2. **Given** a formula version is ready, **When** the Administrador publishes it, **Then** it becomes the active base formula and is available to HU-28 for permitted parameter adjustments.
3. **Given** a formula version is published, **When** a Dirigente adjusts weights under HU-28, **Then** the parameter set and formula structure remain unchanged.
4. **Given** the formula structure or variables must change, **When** an Administrador publishes a new formula version, **Then** the change is recorded as a distinct version with author, timestamp, and previous/new structure and values.
5. **Given** a formula version has been used by a completed ranking, **When** a newer formula is published, **Then** the historical ranking continues to reference the version it used.
6. **Given** an unauthorized role attempts to publish a formula, **When** the request is processed, **Then** the change is denied and no version is created.

### Edge Cases

- Formula version 1 is initialized from [Scoring Model v1](../_shared/scoring-model.md).
- A failed or invalid publication leaves the active formula version unchanged.
- Formula changes do not retroactively rewrite completed rankings.

## Requirements

### Functional Requirements

- **FR-001**: System MUST provide an Administrador with the current formula structure, variables, constants, and initial values.
- **FR-002**: System MUST allow only an Administrador to publish a base formula version.
- **FR-003**: System MUST version each published formula and retain its author, publication time, and change record.
- **FR-004**: System MUST expose the active formula's permitted parameters to HU-28.
- **FR-005**: System MUST preserve the formula version used by each completed ranking.
- **FR-006**: System MUST leave the active formula unchanged when publication validation fails.

### Key Entities

- **BaseFormulaVersion**: version, structure, variables, constants, initial parameter values, author, published at, predecessor.

## Success Criteria

- **SC-001**: Every published formula version has an auditable author, timestamp, and version identifier.
- **SC-002**: HU-28 can only adjust parameters exposed by the active formula version.
- **SC-003**: Completed rankings retain their original formula version reference.

## Assumptions and Decisions to Reconcile

- The current [Scoring Model v1](../_shared/scoring-model.md) is the initial formula and initial publication content.
- HU-28 treats the base formula as pre-defined and limits Dirigente changes to parameters, while HU-27 allows an Administrador to publish a new formula structure. Confirm whether structural formula revisions are included in MVP or whether HU-27 should be reduced to publishing the seeded formula.
- This story does not duplicate HU-28's editing of the permitted scoring parameters. Formula structure changes require a new Administrador-published version, as stated in the backlog.

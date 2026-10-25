# Feature Specification: Score Components Breakdown

**Feature Branch**: `hu-16-score-breakdown`
**Created**: 2026-10-11 | **Revised**: 2026-10-12 (v2)
**Status**: Draft
**Backlog Reference**: HU-16 (Estimate: 3, Priority: Media, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Socio of the club, I want to see the breakdown of which specific actions gave or took away points, so that I understand where my current total score comes from."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Score Components Breakdown (Priority: P2)

As a Socio of the club, I want to see the breakdown of which specific actions gave or took away points, so that I understand where my current total score comes from.

**Why this priority**: Lets Socios verify and understand their score.

**Independent Test**: Log in as a Socio with history and verify the listed components add up exactly to the total shown in HU-14.

**Acceptance Scenarios**:

1. **Given** a Socio in the latest completed ranking, **When** they open the breakdown, **Then** these components are listed: asistencia – frecuencia, asistencia – distancia, participación institucional, antigüedad y edad, bonus nuevo socio, and ajuste por tope.
2. **Given** the list, **When** it renders, **Then** each component shows the points it added or subtracted, with two decimals.
3. **Given** the breakdown, **When** the points are summed, **Then** the sum equals exactly the total shown in HU-14.
4. **Given** a component with a negative value (only "ajuste por tope" can be negative), **When** it renders, **Then** it is shown with a minus sign and an explanation that the score is capped at 100.
5. **Given** a component that explains itself, **When** the Socio expands it, **Then** the underlying figures are shown (for example attended versus counted matches, months of activities, years of seniority).
6. **Given** a Socio not in the latest completed ranking, **When** they open the breakdown, **Then** an informative message is shown instead of an empty list.

---

### Edge Cases

- **Zero components** are listed with 0.00, not hidden, so the structure is always the same.
- **Consistency**: any mismatch between the sum and the HU-14 total is a defect.
- **Rules version**: the screen shows the rules version of the ranking, not the one in force.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list the components defined in the scoring model, from the stored ranking entry.
- **FR-002**: System MUST show the points of each component, rounded to two decimals as stored.
- **FR-003**: System MUST guarantee the sum equals the HU-14 total (the cap adjustment closes the difference).
- **FR-004**: System MUST present the information as read-only.
- **FR-005**: System MUST show an informative message when the Socio has no ranking entry.
- **FR-006**: System MUST show the supporting figures of each component.

### Key Entities

- **ScoreComponent**: ranking entry, component name, points (signed), supporting figures.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of ranking entries have a component sum equal to their total.
- **SC-002**: 100% of Socios without an entry see the informative message.

## Assumptions

- Components are stored by HU-25 per the scoring model; no per-event list is shown in the MVP.
- Priority in the backlog is Media; the Socio's trust in the ranking justifies keeping it in the MVP.

## Revision Notes (v2)

- The component list is now fixed by the model, replacing the vague "variables configured by the Admin".
- Added rounding and cap rules that make the sum verifiable.

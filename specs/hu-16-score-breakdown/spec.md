# Feature Specification: Score Components Breakdown

**Feature Branch**: `hu-16-score-breakdown`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-16 (Estimate: 3, Priority: Media, MVP: Yes)
**Input**: User description: "As a Socio of the club, I want to see the breakdown of which specific actions gave or took away points, so that I understand where my current total score comes from."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Score Components Breakdown (Priority: P2)

As a Socio of the club, I want to see the breakdown of which specific actions gave or took away points, so that I understand where my current total score comes from.

**Why this priority**: Lets Socios verify and understand their score, which supports trust in the ranking.

**Independent Test**: Log in as a Socio with attendance history and verify the listed components add up to the total shown in HU-14.

**Acceptance Scenarios**:

1. **Given** a Socio with score components, **When** they open the breakdown, **Then** a list of actions/components that affected their score is shown (e.g. event attendance, assembly participation, seniority, distance to the club, according to the variables configured by the Dirigente).
2. **Given** the list of components, **When** it renders, **Then** each component shows how many points it added or subtracted.
3. **Given** the breakdown, **When** the points are summed, **Then** the sum equals the total score shown in HU-14.
4. **Given** a Socio with no components registered yet, **When** they open the breakdown, **Then** an informative message is shown instead of an empty list.

---

### Edge Cases

- **Negative components**: components that subtract points are shown with a negative value.
- **Consistency**: any mismatch between the sum of components and the HU-14 total is a defect.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list the actions/components that affected the Socio's score, based on the variables configured by the Dirigente.
- **FR-002**: System MUST show points added or subtracted by each component.
- **FR-003**: System MUST guarantee the sum of components equals the total score shown in HU-14.
- **FR-004**: System MUST present the information as read-only.
- **FR-005**: System MUST show an informative message when the Socio has no components registered.

### Key Entities

- **ScoreComponent**: Socio, variable (e.g. attendance, seniority), points (positive or negative).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of Socios have a component sum equal to their HU-14 total.
- **SC-002**: 100% of Socios without components see the informative message.

## Assumptions

- Components are produced by the ranking calculation (HU-25) from the variables of the scoring formula (HU-28).

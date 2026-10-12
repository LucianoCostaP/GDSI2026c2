# Feature Specification: View Explanation of How the Ranking Works

**Feature Branch**: `hu-13-ranking-explanation`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-13 (Estimate: 1, Priority: Media, MVP: Yes)
**Input**: User description: "As a Socio of the club, I want to consult an explanation of how the ranking and scoring system works, so that I understand which criteria determine my priority for ticket purchase access."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Explanation of How the Ranking Works (Priority: P2)

As a Socio of the club, I want to consult an explanation of how the ranking and scoring system works, so that I understand which criteria determine my priority for ticket purchase access.

**Why this priority**: Transparency about the rules builds trust in the ranking and reduces questions to the club.

**Independent Test**: Log in as a Socio, open the explanation section and verify it describes the current scoring rules in simple language and cannot be edited.

**Acceptance Scenarios**:

1. **Given** a logged-in Socio, **When** they open the ranking explanation section, **Then** a plain-language explanation of how the score is calculated is shown.
2. **Given** the explanation screen, **When** the Socio interacts with it, **Then** it is read-only.
3. **Given** the scoring rules in force changed, **When** the Socio opens the explanation, **Then** it reflects the rules currently in force.
4. **Given** two different Socios, **When** they open the section, **Then** both see the same general explanation, with no per-profile personalization.

---

### Edge Cases

- **Rule changes**: the content shown MUST never describe rules that are no longer in force.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a section, accessible from the system, that explains in simple language how the score is calculated.
- **FR-002**: System MUST present it as read-only to the Socio.
- **FR-003**: System MUST keep the explanation consistent with the scoring rules currently in force.
- **FR-004**: System MUST show the same general explanation to all Socios.

### Key Entities

- **RankingExplanation**: explanatory content tied to the scoring rules version in force.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of Socios see the same explanation.
- **SC-002**: The explanation matches the rules in force after every rules change (HU-28).

## Assumptions

- How the explanation text is kept in sync with the rules (manual copy vs. generated from the rules) is not defined in the backlog and is decided at planning.

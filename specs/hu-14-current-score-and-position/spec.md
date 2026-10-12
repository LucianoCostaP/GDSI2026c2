# Feature Specification: View Current Score and Ranking Position

**Feature Branch**: `hu-14-current-score-and-position`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-14 (Estimate: 3, Priority: Alta, MVP: Yes)
**Input**: User description: "As a Socio of the club, I want to consult my current score and my position in the ranking, so that I know where I stand regarding priority access to ticket purchase."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Current Score and Ranking Position (Priority: P1)

As a Socio of the club, I want to consult my current score and my position in the ranking, so that I know where I stand regarding priority access to ticket purchase.

**Why this priority**: This is the Socio's main reason to use the system: knowing their score and place in line.

**Independent Test**: After a ranking calculation (HU-25), log in as a Socio and verify total score, absolute position ("puesto X de N") and the last update date are shown.

**Acceptance Scenarios**:

1. **Given** a ranking calculated for the Socio, **When** they open the screen, **Then** their current total score is shown.
2. **Given** the same screen, **When** it renders, **Then** their position within the general ranking is shown as an absolute number (e.g. "puesto 342 de 5000 socios").
3. **Given** the same screen, **When** it renders, **Then** the date of the last ranking/score update is shown.
4. **Given** a Socio for whom the ranking has not been calculated yet, **When** they open the screen, **Then** score 0 and the position at the end of the ranking are shown.

---

### Edge Cases

- **Read-only**: nothing on this screen is editable.
- **Not yet calculated**: default is score 0 and last position, never an empty or error state.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST show the Socio's current total score.
- **FR-002**: System MUST show the Socio's position in the general ranking as an absolute number together with the total number of Socios.
- **FR-003**: System MUST show the date of the last ranking/score update.
- **FR-004**: System MUST present this information as read-only.
- **FR-005**: System MUST show score 0 and the final ranking position when the ranking has not been calculated for the Socio.

### Key Entities

- **RankingEntry**: Socio, total score, position. Produced by the ranking calculation (HU-25).
- **Ranking**: calculation version with its last update date and total number of Socios.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of Socios see score, position and last update date consistent with the latest completed ranking.
- **SC-002**: 100% of Socios without a calculated ranking see score 0 and the last position.

## Assumptions

- Ranking data is produced by HU-25; this story only displays it.

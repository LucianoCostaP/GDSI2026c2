# Feature Specification: View Current Score and Ranking Position

**Feature Branch**: `hu-14-current-score-and-position`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3)
**Status**: Draft
**Backlog Reference**: HU-14 (Estimate: 3, Priority: Alta, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Member of the club, I want to consult my current score and my position in the ranking, so that I know where I stand regarding priority access to ticket purchase."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Current Score and Ranking Position (Priority: P1)

As a Member of the club, I want to consult my current score and my position in the ranking, so that I know where I stand regarding priority access to ticket purchase.

**Why this priority**: The Member's main reason to use the system.

**Independent Test**: After a ranking calculation (HU-25), log in as a Member and verify score (0–100, two decimals), "puesto X de N", last update date and rules version.

**Acceptance Scenarios**:

1. **Given** a ranking calculated for the Member, **When** they open the screen, **Then** their current total score is shown on the 0–100 scale with two decimals.
2. **Given** the same screen, **When** it renders, **Then** their position in the general ranking is shown as an absolute number with the total number of ranked Members (for example "puesto 342 de 5000 socios").
3. **Given** the same screen, **When** it renders, **Then** the date and time of the latest completed ranking and the rules version it used are shown.
4. **Given** a Member not included in the latest completed ranking (joined afterwards, or no ranking has ever been calculated), **When** they open the screen, **Then** score 0.00 and the end of the ranking are shown, clearly labeled "provisional: todavía no calculado", and no position is stored for them.
5. **Given** a Member with overdue fees (excluded from the ranking population), **When** they open the screen, **Then** the provisional view is shown with the explanation that the ranking only includes Members with fees up to date, that their history is kept, and that they return to the ranking with their accumulated record once they pay up.
6. **Given** a ranking calculation is running or failed, **When** the Member opens the screen, **Then** the data of the latest **completed** ranking is shown.

---

### Edge Cases

- **Read-only**: nothing on this screen is editable.
- **Never an empty or error state**: the provisional view covers every case without data.
- **Tied scores**: positions are always unique because of the tiebreak (HU-25).
- **Consistency**: the score equals the sum in HU-16.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST show the Member's current total score with two decimals.
- **FR-002**: System MUST show the position as an absolute number together with the total number of ranked Members.
- **FR-003**: System MUST show the date and time of the latest completed ranking and its rules version.
- **FR-004**: System MUST present the information as read-only.
- **FR-005**: System MUST show the labeled provisional view (score 0.00, end of ranking) when the Member is not in the latest completed ranking.
- **FR-006**: System MUST show only data of completed rankings.

### Key Entities

- **RankingEntry**: Member, total score, position, components (see HU-16). Produced by HU-25.
- **Ranking**: calculation version, completed at, rules version, number of ranked Members.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of ranked Members see score, position, date and rules version consistent with the latest completed ranking.
- **SC-002**: 100% of Members not in the ranking see the labeled provisional view.

## Assumptions

- The ranking population is defined in HU-25 (Members with fees up to date).
- For the provisional view the "end of ranking" is shown as the last place of the ranked total; it is a display value only.

## Revision Notes (v2)

- Resolved the clash between "end of ranking" and unique positions by making the view provisional and not stored.
- Added the overdue-fee case, rules version display, and handling of running or failed calculations.
- v3: overdue Members are told their history is kept.

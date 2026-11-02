# Feature Specification: View Current Score and Ranking Position

**Feature Branch**: `hu-14-current-score-and-position`
**Created**: 2026-10-11 | **Revised**: 2026-11-01 (v4)
**Status**: Draft
**Backlog Reference**: HU-14 (Estimate: 3, Priority: Alta, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Socio of the club, I want to consult my current score and my position in the ranking, so that I know where I stand regarding priority access to ticket purchase."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Current Score and Ranking Position (Priority: P1)

As a Socio of the club, I want to consult my current score and my position in the ranking, so that I know where I stand regarding priority access to ticket purchase.

**Why this priority**: The Socio's main reason to use the system.

**Independent Test**: After a ranking calculation (HU-25), log in as a Socio and verify score (0–100, two decimals), "puesto X de N", last update date and rules version.

**Acceptance Scenarios**:

1. **Given** a ranking calculated for the Socio, **When** they open the screen, **Then** their current total score is shown on the 0–100 scale with two decimals.
2. **Given** the same screen, **When** it renders, **Then** their position in the general ranking is shown as an absolute number with the total number of ranked Socios (for example "puesto 342 de 5000 socios").
3. **Given** the same screen, **When** it renders, **Then** the date and time of the latest completed ranking and the rules version it used are shown.
4. **Given** a Socio not included in the latest completed ranking (joined afterwards, or no ranking has ever been calculated), **When** they open the screen, **Then** score 0.00 and the end of the ranking are shown, clearly labeled "Provisional: todavía no calculado", and no position is stored for them. When no ranking has ever been calculated, no position is shown and the screen says that no ranking is available yet.
5. **Given** a Socio with overdue fees (excluded from the ranking population), **When** they open the screen, **Then** the provisional view is shown with the explanation that the ranking only includes Socios with fees up to date, that their history is kept, and that they return to the ranking with their accumulated record once they pay up. This also applies when the Socio appears in the latest completed ranking but their fees are overdue now: this scenario takes precedence over scenarios 1 and 2.
6. **Given** a ranking calculation is running or failed, **When** the Socio opens the screen, **Then** the data of the latest **completed** ranking is shown.

---

### Edge Cases

- **Read-only**: nothing on this screen is editable.
- **Never an empty or error state**: the provisional view covers every case without data.
- **Tied scores**: positions are always unique because of the tiebreak (HU-25).
- **Consistency**: the score equals the sum in HU-16.
- **Fee status at viewing time**: the fee status is read from the club data (the same field that defines the HU-25 population) when the screen is opened, not from the ranking snapshot.
- **Paid up after the ranking**: a Socio who was overdue when the ranking was calculated and is up to date now has no entry; they see the provisional view of scenario 4 until the next calculation includes them.
- **Removed from the club data** (baja in the roster, HU-43): the Socio is out of the HU-25 population and sees the provisional view of scenario 4.
- **Completed ranking with no ranked Socios**: treated like "no ranking available" (no position is shown).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST show the Socio's current total score with two decimals.
- **FR-002**: System MUST show the position as an absolute number together with the total number of ranked Socios.
- **FR-003**: System MUST show the date and time of the latest completed ranking and its rules version.
- **FR-004**: System MUST present the information as read-only.
- **FR-005**: System MUST show the labeled provisional view (score 0.00, end of ranking) when the Socio is not in the latest completed ranking, and no position when there is no ranking with ranked Socios.
- **FR-007**: System MUST show the overdue-fee provisional view whenever the Socio's fees are overdue at viewing time, even if they appear in the latest completed ranking.
- **FR-006**: System MUST show only data of completed rankings.

### Key Entities

- **RankingEntry**: Socio, total score, position, components (see HU-16). Produced by HU-25.
- **Ranking**: calculation version, completed at, rules version, number of ranked Socios.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of ranked Socios see score, position, date and rules version consistent with the latest completed ranking.
- **SC-002**: 100% of Socios not in the ranking see the labeled provisional view.

## Assumptions

- The ranking population is defined in HU-25 (Socios with fees up to date).
- For the provisional view the "end of ranking" is shown as the last place of the ranked total (N in "puesto N de N"); it is a display value only, so it may repeat the position of the last ranked Socio.
- The account is linked to its entry in the club data by club and document number.

## Revision Notes (v2)

- Resolved the clash between "end of ranking" and unique positions by making the view provisional and not stored.
- Added the overdue-fee case, rules version display, and handling of running or failed calculations.
- v3: overdue Socios are told their history is kept.
- v4: the overdue view takes precedence over a stored entry (fee status read at viewing time); a Socio who paid up after the ranking waits for the next calculation; no position when there is no ranking; the provisional position is N; baja follows the HU-25 population. The provisional label starts with a capital letter: "Provisional: todavía no calculado".

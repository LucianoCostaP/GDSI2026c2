# Feature Specification: View Explanation of How the Ranking Works

**Feature Branch**: `hu-13-ranking-explanation`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3)
**Status**: Draft
**Backlog Reference**: HU-13 (Estimate: 1, Priority: Media, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Socio of the club, I want to consult an explanation of how the ranking and scoring system works, so that I understand which criteria determine my priority for ticket purchase access."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Explanation of How the Ranking Works (Priority: P2)

As a Socio of the club, I want to consult an explanation of how the ranking and scoring system works, so that I understand which criteria determine my priority for ticket purchase access.

**Why this priority**: Transparency about the rules builds trust in the ranking.

**Independent Test**: Log in as a Socio, open the explanation, change a weight as Admin (HU-28) and verify the explanation shows the new values.

**Acceptance Scenarios**:

1. **Given** a logged-in Socio, **When** they open the ranking explanation, **Then** a plain-language explanation of the three pillars (asistencia, participación institucional, antigüedad y edad), the new-member bonus and the 0–100 scale is shown, with the **current weights** of the rules in force.
2. **Given** the explanation screen, **When** the Socio interacts with it, **Then** it is read-only.
3. **Given** the rules in force changed (HU-28), **When** the Socio opens the explanation, **Then** it reflects the rules currently in force.
4. **Given** two different Socios, **When** they open the section, **Then** both see the same explanation, with no personalization.
5. **Given** the rules in force differ from the rules used by the latest ranking, **When** the Socio opens the explanation, **Then** a notice says the ranking will reflect them after the next calculation.
6. **Given** the explanation, **When** it describes attendance, **Then** it states that matches of lower demand weigh more and that tiebreaks use seniority, then age, then document number.
7. **Given** the explanation, **When** it describes who appears in the ranking, **Then** it states that only Socios with fees up to date appear, that their history is kept, and that a Socio who pays up returns with their accumulated record.

---

### Edge Cases

- **Rule changes**: the content MUST never describe rules that are no longer in force.
- **Tiebreak wording**: stated generally, without exposing other Socios' data.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a section that explains in simple language how the score is calculated.
- **FR-002**: System MUST present it as read-only.
- **FR-003**: System MUST generate the explanation from the rules version in force (weights and parameters), so it cannot drift from the rules.
- **FR-004**: System MUST show the same explanation to all Socios.
- **FR-005**: System MUST show the notice of scenario 5 when applicable.

### Key Entities

- **RankingExplanation**: static template text plus the values of the rules version in force.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of Socios see the same explanation for the same rules version.
- **SC-002**: After every rules change the explanation shows the new values with no manual edit.

## Assumptions

- Decided: the text is a template filled from the rules version in force (this closes the open question about keeping it in sync).
- Copy is reviewed by the club for plain language.

## Revision Notes (v2)

- Content is now defined by the scoring model and generated from the rules in force.
- Added the notice for rules in force versus the latest ranking.
- v3: added the statement about fee status and kept history.

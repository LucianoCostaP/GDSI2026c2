# Feature Specification: View Upcoming Events

**Feature Branch**: `hu-17-upcoming-events`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-17 (Estimate: 3, Priority: Alta, MVP: Yes)
**Input**: User description: "As a Socio of the club, I want to see the date, time and venue of upcoming events, so that I can plan my attendance in advance."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Upcoming Events (Priority: P1)

As a Socio of the club, I want to see the date, time and venue of upcoming events, so that I can plan my attendance in advance.

**Why this priority**: Socios need to know which events exist and when, both to plan and to know what the reservation process applies to.

**Independent Test**: Publish an event (HU-22), log in as a Socio and verify it appears with date, time and venue, in chronological order.

**Acceptance Scenarios**:

1. **Given** published events enabled for sale/reservation, **When** a Socio opens the events list, **Then** each event is shown with its date, time and venue.
2. **Given** several upcoming events, **When** the list renders, **Then** events are ordered chronologically.
3. **Given** the events list, **When** the Socio interacts with it, **Then** it is read-only.
4. **Given** no upcoming event published, **When** the Socio opens the list, **Then** an informative message is shown instead of an empty list.

---

### Edge Cases

- **Unpublished events**: events in `pending definition` (HU-21) MUST NOT be visible to Socios.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list upcoming published events enabled for sale/reservation, each with date, time and venue.
- **FR-002**: System MUST order events chronologically.
- **FR-003**: System MUST present the list as read-only.
- **FR-004**: System MUST show an informative message when there are no upcoming published events.
- **FR-005**: System MUST NOT show events that have not been published.

### Key Entities

- **Event**: date, time, venue, type, state (`pending definition` / `published`). Created in HU-21, published in HU-22.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of published upcoming events appear, and 0 unpublished events appear.
- **SC-002**: The list is always in chronological order.

## Assumptions

- "Upcoming" means events whose date has not yet passed.

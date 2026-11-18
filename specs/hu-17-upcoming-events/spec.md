# Feature Specification: View Upcoming Events

**Feature Branch**: `hu-17-upcoming-events`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3)
**Status**: Draft
**Backlog Reference**: HU-17 (Estimate: 3, Priority: Alta, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Socio of the club, I want to see the date, time and venue of upcoming events, so that I can plan my attendance in advance."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Upcoming Events (Priority: P1)

As a Socio of the club, I want to see the date, time and venue of upcoming events, so that I can plan my attendance in advance.

**Why this priority**: Socios need to know which events exist and when.

**Independent Test**: Publish an event (HU-22), log in as a Socio and verify it appears with date, time and venue in chronological order, and that an unpublished event does not appear.

**Acceptance Scenarios**:

1. **Given** published events whose start has not passed, **When** a Socio opens the events list, **Then** each event is shown with its date, time, venue and type (Partido or Evento institucional/amateur).
2. **Given** several upcoming events, **When** the list renders, **Then** events are ordered chronologically, soonest first.
3. **Given** the events list, **When** the Socio interacts with it, **Then** it is read-only, except for a link on each event to its slot screen (HU-39).
4. **Given** no upcoming published event, **When** the Socio opens the list, **Then** the message "No hay eventos próximos publicados." is shown instead of an empty list.
5. **Given** an event in state `pending importance definition`, `historical` or `discarded`, **When** the list renders, **Then** it is not shown.
6. **Given** a Socio who arrives from a notification of that event (HU-20, HU-19), **When** the list renders and the event is in it, **Then** the event is highlighted; if it is not in the list, the Socio sees "Este evento ya no está disponible." and the list renders without highlight.

---

### Edge Cases

- **Definition of "enabled for sale/reservation"**: in the MVP it means `published` and start date-time later than now (Buenos Aires time). The list does not depend on whether a wave schedule exists.
- **Event that started**: leaves the list when its start time passes. The rule is the same for Partidos and institutional/amateur events; no event stays visible until the end of its day.
- **Event class** is not shown to Socios.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list upcoming `published` events, each with date, time, venue and type.
- **FR-002**: System MUST order events chronologically.
- **FR-003**: System MUST present the list as read-only.
- **FR-004**: System MUST show "No hay eventos próximos publicados." when there are no upcoming published events.
- **FR-005**: System MUST NOT show events that are not `published`.
- **FR-006**: System MUST offer, per event, navigation to the Socio's own slot (HU-39).
- **FR-007**: System MUST highlight the event referred by a notification when it is in the list, and tell the Socio when it is not.

### Key Entities

- **Event**: date, time, venue, type, class (Partido only), state (`pending importance definition` / `published` / `historical`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of published upcoming events appear and 0 events in other states appear.
- **SC-002**: The list is always in chronological order.

## Assumptions

- "Upcoming" means the event start (date and time) is later than the current time.
- Socios are notified of new events through HU-19 and HU-20 (type `event_published`); this list stays the source of truth. The notification opens this list with the event referred by the `event_id` highlighted (notifications section 3).

## Revision Notes (v2)

- Unified state names, defined "enabled for sale/reservation", and added the link to HU-39.
- v3: shows the event type; capacity removed.
- v4: scenario 6 and FR-007, additive: highlight of the event coming from a notification.

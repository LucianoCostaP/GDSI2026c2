# Feature Specification: Define Event Category (Class A/B/C) or Points and Publish

**Feature Branch**: `hu-22-event-class-and-publication`
**Created**: 2026-10-11 | **Revised**: 2026-11-20 (v5)
**Status**: Draft
**Backlog Reference**: HU-22 (Estimate: 5, Priority: Alta, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an Admin, I want to define the class of a Partido or the points of an institutional/amateur event and publish it, so that I establish how it takes part in the scoring and make it visible to Socios."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Define Event Class or Points and Publish (Priority: P1)

As an Admin, I want to define the importance/weight of an event and publish it, so that the priority criteria for access are set and the event becomes visible to Socios.

**Why this priority**: Publishing makes events visible and fixes the class factor that weights attendance at a Partido in the score.

**Independent Test**: Load a Partido (HU-21), choose its class and publish; verify it becomes `published` and appears in the Socio list. Then load another and let its deadline pass to verify it becomes `expired`, leaves the pending list, cannot be published and is never visible to Socios.

**Acceptance Scenarios**:

1. **Given** events in `pending importance definition`, **When** the Admin opens the pending list, **Then** they see all of them with the time left to their publication deadline.
2. **Given** a pending Partido, **When** the Admin chooses its class (A, B or C) and confirms publication, **Then** the event becomes `published` and visible to Socios (HU-17).
3. **Given** the class chooser, **When** it is shown, **Then** each class shows its meaning and its factor (A = high demand, factor 1.0; B = regular, 1.3; C = low demand, 1.8) and states that a higher factor rewards attendance at lower-demand matches.
4. **Given** a pending Evento institucional/amateur (elections and assemblies included), **When** the Admin defines its points (a whole number from 1 to 100) and confirms publication, **Then** the event becomes `published` and those points are the ones its attendees earn.
5. **Given** a pending event, **When** the Admin publishes it, **Then** the action is accepted only before its publication deadline and while the event start is at least 48 hours away; the deadline is the earlier of 24 hours after its reception (HU-21) and 48 hours before the event start.
6. **Given** a pending event that nobody published, **When** its publication deadline passes, **Then** it becomes `expired`: it is not published, gets no class or points, leaves the pending list, is never visible to Socios (HU-17), accepts no attendance (HU-24) and generates no notification.
7. **Given** an `expired` event, **When** the Admin tries to publish it, **Then** the publication is rejected and the event stays `expired`; there is no way to reopen or extend its deadline.
8. **Given** two Admins act on the same pending event at the same moment, **When** both try to publish it, **Then** exactly one publication takes effect and it is audited.
9. **Given** a published event, **When** the Admin looks for a way to change its class or points, **Then** there is none.

---

### Edge Cases

- **Deadline arithmetic**: because HU-21 requires the start to be at least 48 hours after the reception, the deadline is never earlier than the reception time. An event starting 60 hours after its reception expires 12 hours after it if nobody publishes it.
- **No automatic publication and no job**: nothing is published without an Admin. Expiry needs no scheduler: the event counts as `expired` from the moment its deadline passes, whether or not anything runs at that moment (the state can be derived from the deadline when read). The Admin sees the deadline and the time left in the pending list (scenario 1) to publish in time.
- **Expired is final**: an `expired` event is kept for audit, but it cannot be published, discarded or reopened, and the club's updates to it are omitted (HU-21). If the club still holds the event, it can send it again with a new `id_externo` while the 48-hour lead allows it.
- **Historical and discarded events** (HU-21) are not listed here.
- **Events cancelled by the club** while pending (HU-21) stay pending until the Admin discards them or their deadline passes.
- **Club data** (date, time, venue, type) is read-only here; only the class or the points are adjusted. After publication, changes sent by the club are omitted; outside the MVP, the Admin can reprogram the date and time or withdraw the event (HU-23B), but never change its class or points.
- **Class applies only to Partidos; points apply only to institutional/amateur events.**

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list events pending publication with the time left.
- **FR-002**: System MUST let the Admin define the class (A/B/C) of a Partido, which determines its attendance factor, and the points of an institutional/amateur event, which are the points its attendees earn.
- **FR-003**: System MUST change the event to `published` and make it visible to Socios when publication is confirmed.
- **FR-004**: System MUST allow publication only before the event's publication deadline (the earlier of 24 hours after its reception and 48 hours before the start) and while the start is at least 48 hours away.
- **FR-005**: System MUST treat a pending event whose deadline passed without publication as `expired`: never published, never visible to Socios, without class or points, and not publishable afterwards. It MUST NOT publish any event automatically.
- **FR-006**: System MUST make the transition to `published` atomic and exclusive (compare-and-set on the state).
- **FR-007**: System MUST record which Admin published the event and the class or points chosen.
- **FR-008**: System MUST NOT allow changing the class or points after publication.

### Key Entities

- **Event**: as in HU-21, plus class (Partido) or points (institutional/amateur), published at, and the publication deadline (derived from the reception time and the start).
- **EventClass**: A, B or C with factor (1.0 / 1.3 / 1.8).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 events are published after their publication deadline, and 0 are published without an Admin.
- **SC-002**: 100% of pending events whose deadline passed without publication are `expired` and invisible to Socios.
- **SC-003**: 0 events are published twice.
- **SC-004**: 0 events are published with less than 48 hours before their start.

## Assumptions

- The backlog's former "importance" is the class of a Partido (its attendance factor) or the points of an institutional/amateur event (its participation points), defined by whoever publishes the event. Both are fixed at publication.
- The notification of a publication (`event_published`, HU-19) is generated by calling the notification contract after the publication commits. An event that expires generates no notification. A failed notification never undoes or delays the publication (notifications section 1). Out of this spec: the email notification of class changes after a reprogramming (HU-23).
- A wrong class cannot be fixed after publication; the confirmation step must show the class clearly.

## Revision Notes

- v3: added the 48-hour publication lead and the resulting deadline; class applies only to Partidos; institutional/amateur events publish without a class.
- v3.1: institutional/amateur events (elections and assemblies included) get their points when published.
- v3.4: the base data comes from the club (HU-21); here the Admin adjusts only the class or the points.
- v4: title and input as in the backlog; the deadline counts from the reception of the event (the club sends it); no dependency on the club at the deadline; HU-23 is outside the MVP.
- v4.1: HU-23B replaces HU-23; after publication the Admin can reprogram the date and time or withdraw the event, never change the class or points (decision 62).
- v5: no automatic publication; a pending event whose deadline passes without publication becomes `expired` (final, never visible, never scored) and there is no publication job or default class or points at the deadline (decision 65).

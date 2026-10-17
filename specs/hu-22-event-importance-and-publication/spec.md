# Feature Specification: Define Event Class or Points and Publish

**Feature Branch**: `hu-22-event-importance-and-publication`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3)
**Status**: Draft
**Backlog Reference**: HU-22 (Estimate: 5, Priority: Alta, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an Admin, I want to define the importance/weight of an event and publish it, so that the priority criteria for access are set and the event becomes visible to Members."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Define Event Class or Points and Publish (Priority: P1)

As an Admin, I want to define the importance/weight of an event and publish it, so that the priority criteria for access are set and the event becomes visible to Members.

**Why this priority**: Publishing makes events visible and fixes the class factor that weights attendance at a Partido in the score.

**Independent Test**: Load a Partido (HU-21), choose its class and publish; verify it becomes `published` and appears in the Member list. Then load another and let its deadline pass to verify the default class and automatic publication.

**Acceptance Scenarios**:

1. **Given** events in `pending importance definition`, **When** the Admin opens the pending list, **Then** they see all of them with the time left to their publication deadline.
2. **Given** a pending Partido, **When** the Admin chooses its class (A, B or C) and confirms publication, **Then** the event becomes `published` and visible to Members (HU-17).
3. **Given** the class chooser, **When** it is shown, **Then** each class shows its meaning and its factor (A = high demand, factor 1.0; B = regular, 1.3; C = low demand, 1.8) and states that a higher factor rewards attendance at lower-demand matches.
4. **Given** a pending Evento institucional/amateur (elections and assemblies included), **When** the Admin defines its points (a whole number from 1 to 100) and confirms publication, **Then** the event becomes `published` and those points are the ones its attendees earn.
5. **Given** a pending event, **When** the Admin publishes manually, **Then** the action is accepted only while the event start is at least 48 hours away.
6. **Given** a pending event, **When** its publication deadline arrives, **Then** it is published automatically: the deadline is the earlier of 24 hours after its import and 48 hours before the event start. A Partido without a chosen class gets the default class and an institutional/amateur event without points gets the default points (both system settings, proposed Clase B and 20 points). The publication is recorded as made by the system.
7. **Given** the Admin published before the deadline, **When** the deadline arrives, **Then** nothing happens automatically.
8. **Given** the Admin and the scheduler act at the same moment, **When** both try to publish, **Then** exactly one publication takes effect and it is audited.
9. **Given** a published event, **When** the Admin looks for a way to change its class or points, **Then** there is none, except during the 24-hour window that opens after a reprogramming (HU-23).

---

### Edge Cases

- **Deadline arithmetic**: because HU-21 requires the start to be at least 48 hours after the import, the deadline is never earlier than the import time. An event starting 60 hours after the import is published automatically 12 hours after it.
- **Club API at the deadline**: the automatic publication does not depend on the club API. If the API cannot be reached at the deadline, the event is published as it was imported (the check of HU-21 repeats at the next refresh).
- **Scheduler failure**: the publication job is idempotent, runs at least every minute and retries; a missed run publishes on the next run and is flagged in the audit, unless the 48-hour lead was lost, in which case the Admin is warned on screen.
- **Historical and discarded events** (HU-21) are not listed here.
- **Events flagged by HU-21** (the club no longer lists them) are not published automatically.
- **Club data** (date, time, venue, type) is read-only here; only the class or the points are adjusted. After publication the club data is refreshed only through HU-23.
- **Class applies only to Partidos; points apply only to institutional/amateur events.**

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list events pending publication with the time left.
- **FR-002**: System MUST let the Admin define the class (A/B/C) of a Partido, which determines its attendance factor, and the points of an institutional/amateur event, which are the points its attendees earn.
- **FR-003**: System MUST change the event to `published` and make it visible to Members when publication is confirmed.
- **FR-004**: System MUST allow manual publication only while the event start is at least 48 hours away.
- **FR-005**: System MUST publish automatically at the earlier of 24 hours after its import and 48 hours before the start, applying the default class to a Partido without class and the default points to an institutional/amateur event without points.
- **FR-006**: System MUST make the transition to `published` atomic and exclusive (compare-and-set on the state).
- **FR-007**: System MUST record who published (Admin or system) and whether the class was chosen or default.
- **FR-008**: System MUST NOT allow changing the class or points after publication, except during the 24-hour window that opens after a reprogramming (HU-23).

### Key Entities

- **Event**: as in HU-21, plus class (Partido) or points (institutional/amateur), and published at.
- **EventClass**: A, B or C with factor (1.0 / 1.3 / 1.8) and the default flag.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of pending events are published, manually or automatically, by their deadline, with the automatic ones within 2 minutes of it.
- **SC-002**: 100% of automatically published events without a defined class or points carry the defaults.
- **SC-003**: 0 events are published twice.
- **SC-004**: 0 events are published with less than 48 hours before their start.

## Assumptions

- "Importance" is the class of a Partido (its attendance factor) or the points of an institutional/amateur event (its participation points), defined by whoever publishes the event. Both are fixed at publication.
- Out of this spec because they depend on stories outside the MVP: the email on publication (HU-19) and the email notification of class changes after a reprogramming.
- Outside the HU-23 window a wrong class cannot be fixed; the confirmation step must show the class clearly.

## Revision Notes (v3)

- Added the 48-hour publication lead and the resulting deadline; class applies only to Partidos; institutional/amateur events publish without a class.
- v3.1: institutional/amateur events (elections and assemblies included) get their points when published.
- v3.4: the base data comes from the club (HU-21); here the Admin adjusts only the class or the points.

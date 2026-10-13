# Feature Specification: Define Event Class and Publish

**Feature Branch**: `hu-22-event-importance-and-publication`
**Created**: 2026-10-11 | **Revised**: 2026-10-12 (v2)
**Status**: Draft
**Backlog Reference**: HU-22 (Estimate: 5, Priority: Alta, MVP: Yes)
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an Administrador, I want to define the importance/weight of an event and publish it, so that the priority criteria for access are set and the event becomes visible to Socios."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Define Event Class and Publish (Priority: P1)

As an Administrador, I want to define the importance/weight of an event and publish it, so that the priority criteria for access are set and the event becomes visible to Socios.

**Why this priority**: Publishing makes events visible and fixes the class factor that weights attendance in the score.

**Independent Test**: Load an event (HU-21), choose its class and publish; verify it becomes `published` and appears in the Socio list. Then load another and let 24 hours pass to verify the default class and automatic publication.

**Acceptance Scenarios**:

1. **Given** events in `pending importance definition`, **When** the Administrador opens the pending list, **Then** they see all of them with the time left to their deadline.
2. **Given** a pending event, **When** the Administrador chooses its class (A, B or C) and confirms publication, **Then** the event becomes `published` and visible to Socios (HU-17).
3. **Given** the class chooser, **When** it is shown, **Then** each class shows its meaning and its factor (A = high demand, factor 1.0; B = regular, 1.3; C = low demand, 1.8) and states that a higher factor rewards attendance at lower-demand matches.
4. **Given** an event loaded less than 24 hours ago, **When** the Administrador defines the class and publishes, **Then** the action is accepted.
5. **Given** an event whose class was not defined within 24 hours of loading, **When** the 24 hours elapse, **Then** the default class (Clase B, a system setting) is applied and the event is published automatically, recorded as published by the system.
6. **Given** the Administrador published before the deadline, **When** the deadline arrives, **Then** nothing happens automatically.
7. **Given** the Administrador and the scheduler act at the same moment, **When** both try to publish, **Then** exactly one publication takes effect and it is audited.
8. **Given** a published event, **When** the Administrador looks for a way to change its class, **Then** there is none in the MVP.

---

### Edge Cases

- **24-hour boundary**: the window runs from the moment HU-21 saved the event; the automatic publication fires at its end.
- **Scheduler failure**: the publication job is idempotent, runs at least every minute and retries; a missed run publishes on the next run and is flagged in the audit.
- **Historical events** (HU-21) are not listed here.
- **Capacity** must exist before publishing (it is required in HU-21).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list events pending class definition with the time left.
- **FR-002**: System MUST let the Administrador define the event class (A/B/C); the class determines the attendance factor used by the scoring model.
- **FR-003**: System MUST change the event to `published` and make it visible to Socios when publication is confirmed.
- **FR-004**: System MUST give 24 hours from the loading of the base information to define the class and publish.
- **FR-005**: System MUST automatically apply the default class and publish if the class was not defined within 24 hours.
- **FR-006**: System MUST make the transition to `published` atomic and exclusive (compare-and-set on the state).
- **FR-007**: System MUST record who published (Administrador or system) and whether the class was chosen or default.
- **FR-008**: System MUST NOT allow changing the class after publication in the MVP.

### Key Entities

- **Event**: as in HU-21, plus class and published at.
- **EventClass**: A, B or C with factor (1.0 / 1.3 / 1.8) and the default flag.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of pending events are published, manually or automatically, within 24 hours of loading, with the automatic ones within 2 minutes of the deadline.
- **SC-002**: 100% of automatically published events carry the default class.
- **SC-003**: 0 events are published twice.

## Assumptions

- Decided: "importance" is the event class; it replaces the ambiguous "scoring rules or quota", and its only effect in the MVP is the attendance factor.
- Out of this spec because they depend on stories outside the MVP: the email on publication (HU-19) and class changes after reprogramming with notification (HU-23).
- Since there is no change after publication, a wrong class cannot be fixed in the MVP; the confirmation step must show the class clearly.

## Revision Notes (v2)

- Importance is now defined (A/B/C and factors) and consumed by the scoring model.
- Added scheduler requirements, atomic exclusive publication, audit and the no-change-after-publication rule.

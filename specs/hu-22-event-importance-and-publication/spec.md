# Feature Specification: Define Event Importance and Publish

**Feature Branch**: `hu-22-event-importance-and-publication`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-22 (Estimate: 5, Priority: Alta, MVP: Yes)
**Input**: User description: "As an Administrador, I want to define the importance/weight of an event and publish it, so that the priority criteria for access are set and the event becomes visible to Socios."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Define Event Importance and Publish (Priority: P1)

As an Administrador, I want to define the importance/weight of an event and publish it, so that the priority criteria for access are set and the event becomes visible to Socios.

**Why this priority**: Publishing makes events visible to Socios and fixes the importance that drives scoring rules and quota, so every later step (attendance, segmentation, reservation) depends on it.

**Independent Test**: Load an event (HU-21), define its importance and publish; verify it becomes `published` and appears in the Socio list. Then load another and wait out the 24 hours to verify default importance and automatic publication.

**Acceptance Scenarios**:

1. **Given** events loaded earlier and pending definition, **When** the Administrador opens the pending list, **Then** they see all of them.
2. **Given** a pending event, **When** the Administrador defines its importance/category, which determines the scoring rules or quota that apply, and confirms publication, **Then** the event becomes `published` and visible to Socios (HU-17).
3. **Given** an event whose base information was loaded less than 24 hours ago, **When** the Administrador defines importance and publishes, **Then** the action is accepted.
4. **Given** an event whose importance was not defined within 24 hours of loading its base information, **When** the 24 hours elapse, **Then** a pre-established default importance/weight is applied and the event is published automatically, without manual intervention.

---

### Edge Cases

- **24-hour boundary**: the window runs from the moment HU-21 saved the event; the automatic publication fires at its end.
- **Manual vs. automatic**: if the Administrador publishes before the deadline, no automatic action happens afterwards.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list events loaded previously and pending importance definition.
- **FR-002**: System MUST let the Administrador define the importance/category of an event, which determines the scoring rules or quota that apply.
- **FR-003**: System MUST change the event to `published` and make it visible to Socios (HU-17) when publication is confirmed.
- **FR-004**: System MUST give 24 hours from the loading of the base information to define importance and publish.
- **FR-005**: System MUST automatically apply a pre-established default importance/weight and publish the event if importance was not defined within 24 hours.

### Key Entities

- **Event**: as in HU-21, plus importance/category and published at.
- **ImportanceCategory**: importance/weight level assignable to an event, including the pre-established default.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of pending events are published, manually or automatically, within 24 hours of loading.
- **SC-002**: 100% of automatically published events carry the default importance.

## Assumptions

- Out of this spec's scope because they depend on stories outside the MVP: the email to Socios on publication (HU-19), and the post-publication importance changes after a reprogramming with their notification (HU-23). They are tracked in the README.
- The default importance/weight value is a system setting not defined in the backlog.

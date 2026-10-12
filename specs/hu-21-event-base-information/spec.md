# Feature Specification: Load Event Base Information

**Feature Branch**: `hu-21-event-base-information`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-21 (Estimate: 3, Priority: Alta, MVP: Yes)
**Input**: User description: "As a System Administrator, I want to load the base information of an upcoming event (date, time, venue, type), so that it can later be reviewed and have its importance and priority rules defined."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Load Event Base Information (Priority: P1)

As a System Administrator, I want to load the base information of an upcoming event (date, time, venue, type), so that it can later be reviewed and have its importance and priority rules defined.

**Why this priority**: First step of the event lifecycle: no event can be published or segmented until its base data exists.

**Independent Test**: As an Administrador, load a new event and verify it is saved as `pending importance definition` and does not appear in the Socio events list.

**Acceptance Scenarios**:

1. **Given** an Administrador logged in, **When** they enter date, time, venue and type of an event and save, **Then** the event is saved.
2. **Given** a saved event, **When** it is listed in the admin view, **Then** its state is `pending importance definition`, ready to be reviewed and completed (HU-22).
3. **Given** a saved event not yet published, **When** a Socio opens the events list (HU-17), **Then** the event is not visible.

---

### Edge Cases

- **Missing fields**: saving without date, time, venue or type is blocked with a validation message (inferred; not stated in the backlog).
- **Capacity**: the backlog does not list ticket/seat capacity among the fields (see Assumptions).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let the Administrador enter date, time, venue and type of an event.
- **FR-002**: System MUST save the event in state `pending importance definition` and keep it available for later review and completion.
- **FR-003**: System MUST NOT show the event to Socios at this step.
- **FR-004**: System MUST record the moment the base information was loaded, as it starts the 24-hour window defined in HU-22.

### Key Entities

- **Event**: date, time, venue, type, state (`pending importance definition` / `published`), base-information loaded at.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of saved events start in `pending importance definition`.
- **SC-002**: 0 events in this state are visible to Socios.

## Assumptions

- Event capacity (entries/seats), needed by HU-36 to compute the number of waves, is not captured by this story's acceptance criteria; it must be provided here or in HU-22 (see README, open questions).
- Editing an event after saving is covered by HU-23, which is not in the MVP.

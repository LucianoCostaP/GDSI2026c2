# Feature Specification: Load Event Base Information

**Feature Branch**: `hu-21-event-base-information`
**Created**: 2026-10-11 | **Revised**: 2026-10-12 (v2)
**Status**: Draft
**Backlog Reference**: HU-21 (Estimate: 3, Priority: Alta, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md)
**Input**: "As a System Administrator, I want to load the base information of an upcoming event (date, time, venue, type), so that it can later be reviewed and have its importance and priority rules defined."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Load Event Base Information (Priority: P1)

As a System Administrator, I want to load the base information of an upcoming event (date, time, venue, type), so that it can later be reviewed and have its importance and priority rules defined.

**Why this priority**: First step of the event lifecycle: no event can be published, segmented or scored until its data exists.

**Independent Test**: As an Administrador, load a new event and verify it is saved as `pending importance definition`, that the 24-hour deadline is recorded, and that it does not appear in the Socio events list.

**Acceptance Scenarios**:

1. **Given** an Administrador logged in, **When** they enter date, time, venue, type and capacity of a future event and save, **Then** the event is saved.
2. **Given** a saved event, **When** it is listed in the admin view, **Then** its state is `pending importance definition` and the time left to the 24-hour deadline is shown (HU-22).
3. **Given** a saved event not yet published, **When** a Socio opens the events list (HU-17), **Then** the event is not visible.
4. **Given** an event in `pending importance definition`, **When** the Administrador edits its base information, **Then** the change is saved and the 24-hour deadline does not restart.
5. **Given** an Administrador loading a **past** event to give the scoring its history (for example last year's matches), **When** they confirm it is a historical load and choose its class (A/B/C), **Then** the event is saved as `historical`, is never visible to Socios, never goes through publication and can receive attendance (HU-24).
6. **Given** a missing or invalid field, **When** saving, **Then** it is blocked with a validation message naming the field.
7. **Given** an upcoming event whose start is less than 24 hours after the loading time, **When** saving, **Then** it is rejected with an explanation. [NEEDS CLARIFICATION: not in the backlog; it avoids an automatic publication after the event starts.]

---

### Edge Cases

- **Capacity**: positive integer, number of tickets or seats available for Socios. It feeds the number of waves (HU-36).
- **Type**: chosen from a catalog (for example "Partido oficial", "Otro evento"). Only "Partido oficial" counts for scoring. [NEEDS CLARIFICATION: confirm the catalog.]
- **Duplicates**: same date, time and venue as an existing event is blocked.
- **After publication**: the base information cannot be edited in the MVP (reprogramming is HU-23, outside the MVP). See Assumptions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let the Administrador enter date, time, venue, type and capacity of an event.
- **FR-002**: System MUST save a future event in state `pending importance definition` and keep it available for review and completion.
- **FR-003**: System MUST NOT show the event to Socios at this step.
- **FR-004**: System MUST record the moment the base information was loaded, as it starts the 24-hour window defined in HU-22.
- **FR-005**: System MUST allow editing base information while the event is `pending importance definition`, without restarting the window.
- **FR-006**: System MUST support a historical load of past events with their class, saved as `historical`.
- **FR-007**: System MUST validate required fields, capacity, duplicates and the 24-hour minimum lead time.
- **FR-008**: System MUST audit every creation and edit.

### Key Entities

- **Event**: date, time, venue, type, capacity, class (set by HU-22 or at historical load), state (`pending importance definition` / `published` / `historical`), base information loaded at.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of saved upcoming events start in `pending importance definition` with the loading time recorded.
- **SC-002**: 0 events in this state or in `historical` are visible to Socios.

## Assumptions

- Capacity is now a required field (this closes the gap that blocked HU-36).
- Residual risk: a data-entry error in a **published** event cannot be corrected in the MVP and the event keeps its default or chosen class. Recommend pulling a minimal version of HU-23 into the MVP.

## Revision Notes (v2)

- Added capacity, type catalog, editing while pending, historical load for past years' data, duplicate and lead-time validation.

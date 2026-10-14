# Feature Specification: Import Event Base Information from the Club API

**Feature Branch**: `hu-21-event-base-information`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3.4)
**Status**: Draft
**Backlog Reference**: HU-21 (Estimate: 3, Priority: Alta, MVP: Yes). Re-estimate: uses the club API client and adds refresh, discard and historical import.
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md)
**Input**: "As a System Administrator, I want to bring an upcoming event from the club's data (date, time, venue, type), so that it can later be reviewed and have its importance and priority rules defined."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Import Event Base Information (Priority: P1)

As a System Administrator, I want to bring an upcoming event from the club's data (date, time, venue, type), so that it can later be reviewed and have its importance and priority rules defined. The club organizes the events and is the source of truth; the system takes the data from the club API and the Administrador adjusts only the scoring parameters (class or points) when publishing.

**Why this priority**: First step of the event lifecycle: no event can be published, segmented or scored until it exists in the system.

**Independent Test**: As an Administrador, import an upcoming event from the club's list and verify it is saved as `pending importance definition` with the club's data, that the publication deadline is recorded, and that it does not appear in the Socio events list.

**Acceptance Scenarios**:

1. **Given** an Administrador logged in, **When** they open "Importar evento del club", **Then** the system asks the club API and lists the club's upcoming events not yet imported, each with date, time, venue and type (Partido or Evento institucional/amateur).
2. **Given** the list, **When** the Administrador selects one or more events and confirms, **Then** each event is created in state `pending importance definition` with the club's data and the club's event reference, and the import time is recorded.
3. **Given** a saved event, **When** it is listed in the admin view, **Then** its state is `pending importance definition` and the time left to its publication deadline is shown (HU-22).
4. **Given** a saved event not yet published, **When** a Socio opens the events list (HU-17), **Then** the event is not visible.
5. **Given** an event in `pending importance definition`, **When** the Administrador looks at its date, time, venue and type, **Then** they are read-only: they belong to the club.
6. **Given** an event in `pending importance definition`, **When** the Administrador asks to refresh it from the club (for example the club rescheduled it), **Then** the data is updated from the API, the publication window does not restart, and the new start must still respect the 48-hour publication lead. If the club moved it to less than 48 hours from now, the refresh is refused with the reason, because the event could no longer be published with the minimum lead, and the Administrador can discard it.
7. **Given** a pending event the club no longer lists, **When** the system detects it at a refresh or at its publication deadline, **Then** the event is flagged, it is not published automatically, and the Administrador can discard it (state `discarded`: never visible, never scored). If the API cannot be reached at the deadline, the event is published as imported.
8. **Given** the club's list, **When** an event starts less than 48 hours from now, **Then** it appears but cannot be imported, with the reason (it could not be published with the minimum 48-hour lead).
9. **Given** an event already imported, **When** the list is shown, **Then** it is not offered again (the club's event reference is unique).
10. **Given** an Administrador importing **past** events to give the scoring its history (for example last year's matches), **When** they choose a date range, **Then** the club's past events in that range are listed, the Administrador sets the class (A/B/C) of each Partido and the points of each institutional/amateur event (prefilled with the defaults), and on confirmation they are saved as `historical`: never visible to Socios, never published, able to receive attendance (HU-24).
11. **Given** the club API is unavailable, times out, is not authorized or answers with an unexpected structure, **When** the Administrador opens the import, **Then** an error is shown and no event is created.
12. **Given** a club event with missing or unknown date, venue or type, **When** the list is shown, **Then** it is flagged as incomplete and cannot be imported.

---

### Edge Cases

- **Type** is given by the club: **Partido** (counts in the attendance pillar, needs a class, takes part in waves) or **Evento institucional/amateur** (counts in the institutional pillar, has no class and no waves, and its points are set at publication, also for elections and assemblies). Every Partido takes place at the club stadium; events held elsewhere are institutional/amateur.
- **Adjustable by the Administrador**: only the class (A/B/C) of a Partido or the points of an institutional/amateur event, defined in HU-22 (or at the historical import).
- **Reference**: the club's event reference is unique and is the key HU-24 uses to ask for attendance.
- **After publication**: the club data is refreshed only through HU-23 (reprogramming), a minimal version of which is proposed for the MVP.
- **Volume**: the list is paginated; only upcoming events within the club's published horizon are shown.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list the club's upcoming events, not yet imported, from the club API.
- **FR-002**: System MUST create each selected event in state `pending importance definition` with the club's data and reference, and keep it available for review and completion.
- **FR-003**: System MUST NOT show the event to Socios at this step.
- **FR-004**: System MUST record the import time, as it starts the publication window defined in HU-22.
- **FR-005**: System MUST make the club's data read-only and allow a refresh from the club while the event is `pending importance definition`, without restarting the window.
- **FR-006**: System MUST flag a pending event that the club no longer lists or that could no longer be published with the 48-hour lead, withhold its automatic publication, and let the Administrador discard it.
- **FR-007**: System MUST allow importing past events as `historical`, with class or points set by the Administrador.
- **FR-008**: System MUST validate that the data is complete, that the type is known, that the reference is not already imported, and the 48-hour minimum lead.
- **FR-009**: System MUST persist nothing when the API fails.
- **FR-010**: System MUST audit every import, refresh, discard and historical import.

### Key Entities

- **Event**: club event reference (unique), date, time, venue, type (`Partido` / `Evento institucional/amateur`), class (Partido only) or points (institutional/amateur only), state (`pending importance definition` / `published` / `historical` / `discarded` / `withdrawn`), imported at, last refreshed at.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of imported upcoming events start in `pending importance definition` with the import time recorded.
- **SC-002**: 0 events in `pending importance definition`, `historical` or `discarded` are visible to Socios.
- **SC-003**: 0 upcoming events are imported with a start less than 48 hours away.
- **SC-004**: 0 events are imported twice.

## Assumptions

- The club API exposes upcoming and past events with a unique reference, date, time, venue and type, and the club organizes them (confirmed by the product owner).
- Capacity is not captured: the waves are percentile-based (HU-36) and do not need it.
- The 48-hour lead is the minimum time between publication and the event start.
- Clubs reschedule matches often: a **published** event is refreshed from the club through HU-23. Without HU-23 Socios would see an outdated date.

## Revision Notes

- v2: type catalog, historical load, editing while pending, lead time.
- v3: lead time changed from 24 to 48 hours as the minimum publication lead; capacity removed.
- v3.4: events are imported from the club API instead of typed in; club data is read-only; added refresh, discard of events the club no longer lists and historical import from the API.

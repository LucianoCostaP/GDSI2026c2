# Feature Specification: View Own Assigned Slot

**Feature Branch**: `hu-39-own-reservation-slot`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-39 (Estimate: 2, Priority: Alta, MVP: Yes)
**Input**: User description: "As a Socio of the club, I want to consult the date and time at which my own reservation access opens, so that I know from when I can reserve my turn for that event."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Own Assigned Slot (Priority: P1)

As a Socio of the club, I want to consult the date and time at which my own reservation access opens, so that I know from when I can reserve my turn for that event.

**Why this priority**: Each Socio needs to know their own opening time; without it the waves schedule has no practical effect.

**Independent Test**: With a generated schedule, view the screen as Socios from different waves and verify wave, date/time and the three time states (before, during, excluded).

**Acceptance Scenarios**:

1. **Given** a Socio included in a segmentation, **When** they open the screen, **Then** they see the wave they belong to according to their ranking position, with its enablement date/time.
2. **Given** the wave's enablement date has passed, **When** the Socio opens the screen, **Then** they are told access is already enabled and until when they can reserve (general closing date).
3. **Given** the wave is not enabled yet, **When** the Socio opens the screen, **Then** they are told how much time remains until they can access.
4. **Given** a Socio excluded from segmentation (received a transferred seat), **When** they open the screen, **Then** they are told no turn applies to them for that event, and why.

---

### Edge Cases

- **Read-only**: nothing on this screen is editable.
- **No schedule yet**: if the event has no schedule, the Socio is informed instead of seeing an empty screen (to confirm; not stated in this story).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST show the Socio's wave, based on their ranking position, with its enablement date/time.
- **FR-002**: System MUST tell the Socio access is already enabled and until when, if the wave's date has passed.
- **FR-003**: System MUST tell the Socio how much time remains if the wave is not enabled yet.
- **FR-004**: System MUST tell excluded Socios that no turn applies to them and why.
- **FR-005**: System MUST present the information as read-only.

### Key Entities

- **Wave** and **WaveSchedule**: as in HU-36 and HU-37, consulted per Socio.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of included Socios see the wave and enablement date matching the generated schedule.
- **SC-002**: 100% of excluded Socios see the explanation instead of a wave.

## Assumptions

- Excluded Socios exist only if seat transfer exists (not in the MVP); the case is specified for completeness.

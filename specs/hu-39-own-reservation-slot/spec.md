# Feature Specification: View Own Assigned Slot

**Feature Branch**: `hu-39-own-reservation-slot`
**Created**: 2026-10-11 | **Revised**: 2026-10-12 (v2)
**Status**: Draft
**Backlog Reference**: HU-39 (Estimate: 2, Priority: Alta, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Socio of the club, I want to consult the date and time at which my own reservation access opens, so that I know from when I can reserve my turn for that event."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Own Assigned Slot (Priority: P1)

As a Socio of the club, I want to consult the date and time at which my own reservation access opens, so that I know from when I can reserve my turn for that event.

**Why this priority**: Without it the wave schedule has no practical effect for the Socio.

**Independent Test**: With a confirmed schedule, view the screen as Socios from different waves and verify the wave, the date and time, and each of the states: before, open, closed, not in a wave, no schedule.

**Acceptance Scenarios**:

1. **Given** a Socio included in a segmentation with a confirmed schedule, **When** they open the screen for an event (from HU-17), **Then** they see the wave they belong to (as stored in the segmentation) with its enablement date and time.
2. **Given** the wave's enablement time has passed and the general closing has not, **When** the Socio opens the screen, **Then** they are told access is already enabled and until when (the general closing).
3. **Given** the wave is not enabled yet, **When** the Socio opens the screen, **Then** they are told how much time remains, computed from the server clock.
4. **Given** the general closing has passed, **When** the Socio opens the screen, **Then** they are told the reservation period is closed.
5. **Given** the event has a segmentation but the Socio is not in any wave (joined or became up to date after the segmentation), **When** they open the screen, **Then** they are told that no turn was assigned and that they should contact the club.
6. **Given** the event has no confirmed schedule, **When** the Socio opens the screen, **Then** they are informed that the schedule is not defined yet, instead of seeing an empty screen.
7. **Given** a Socio with overdue fees, **When** they open the screen, **Then** they get the message of scenario 5.

---

### Edge Cases

- **Read-only**: nothing on this screen is editable.
- **The wave is the stored one**: later ranking recalculations do not move the Socio between waves.
- **Access meaning**: "enabled" is informative; purchase happens on the club's external ticketing platform.
- **Excluded by seat transfer**: not applicable in the MVP (the transfer feature is not in scope).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST show the Socio's wave, as stored in the segmentation, with its enablement date and time.
- **FR-002**: System MUST tell the Socio access is already enabled and until when, if the wave's time has passed and the period is open.
- **FR-003**: System MUST tell the Socio how much time remains if the wave is not enabled yet.
- **FR-004**: System MUST tell the Socio when the reservation period has closed.
- **FR-005**: System MUST handle a Socio outside the segmentation and an event with no confirmed schedule with explanatory messages.
- **FR-006**: System MUST present the information as read-only.

### Key Entities

- **Wave** and **WaveSchedule**: as in HU-36 and HU-37, consulted per Socio.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of included Socios see the wave and enablement time matching the confirmed schedule.
- **SC-002**: 100% of Socios outside any wave see the explanation instead of a wave.
- **SC-003**: Countdowns use the server clock; a test with a skewed device clock shows the same value.

## Assumptions

- The Socio reaches this screen from the events list (HU-17).

## Revision Notes (v2)

- Added the closed, not-in-wave and no-schedule states, server-clock countdown and the link from HU-17.
- Replaced the non-testable "excluded by transfer" case with the real "outside the segmentation" case.

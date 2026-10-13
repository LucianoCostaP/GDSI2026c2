# Feature Specification: Automatic Wave Schedule Generation

**Feature Branch**: `hu-37-wave-schedule-generation`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3)
**Status**: Draft
**Backlog Reference**: HU-37 (Estimate: 3, Priority: Alta, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a System Administrator, I want to automatically generate the enablement dates of each segmented wave, so that I define when reservation access opens for each group of Socios without assigning dates one by one."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic Wave Schedule Generation (Priority: P1)

As a System Administrator, I want to automatically generate the enablement dates of each segmented wave, so that I define when reservation access opens for each group of Socios without assigning dates one by one.

**Why this priority**: Turns the segmentation into a timeline that Socios can follow.

**Independent Test**: With an existing segmentation, define opening and closing and verify start dates are evenly spaced, highest percentile first, and shown to the Administrador.

**Acceptance Scenarios**:

1. **Given** an event without segmentation, **When** the Administrador tries to generate the schedule, **Then** it is not possible, as it requires an existing segmentation (HU-36).
2. **Given** an existing segmentation, **When** the Administrador defines the total reservation period (opening of the first wave and general closing, date and time), **Then** the period is validated and accepted.
3. **Given** a defined period, **When** the schedule is generated, **Then** wave i starts at `opening + (i − 1) × (closing − opening) / N`, in order, wave 1 (highest percentile) first.
4. **Given** a generated schedule, **When** the Administrador reviews it, **Then** they see each wave with its start time, the closing time and the number of Socios, and must confirm it before Socios can see it.
5. **Given** a wave that reaches its start date/time, **When** it is enabled, **Then** access stays open for that wave and all previous ones until the general closing.
6. **Given** a confirmed schedule, **When** the first wave has not opened, **Then** the Administrador may regenerate it after a confirmation, replacing the previous schedule.
7. **Given** the first wave has opened, **When** the Administrador tries to regenerate, **Then** it is blocked.

---

### Edge Cases

- **Invalid period**: the opening must be in the future, the closing after the opening, the closing not after the event start, and the step between waves at least the minimum (default 5 minutes). Otherwise the period is rejected with the reason.
- **Fewer waves**: waves with no Socios (very small rankings) are omitted by HU-36; the schedule covers only the waves that exist.
- **Only for Partido events**: institutional/amateur events have no waves.
- **Event withdrawn** (HU-23): the schedule is voided and no wave opens.
- **Event rescheduled** (HU-23): the schedule is kept, invalidated or has its closing moved, depending on the new start (rules in HU-23).
- **Segmentation regenerated** (HU-36): the schedule is invalidated and must be generated again.
- **Scope of "access"**: in the MVP the schedule is informative. The club's external ticketing platform manages availability and purchase; this system does not take or enforce reservations (HU-40 is outside the MVP).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST only generate a schedule over an existing, valid segmentation.
- **FR-002**: System MUST let the Administrador define the total reservation period (first wave opening and general closing date/time).
- **FR-003**: System MUST distribute wave start times evenly within the period, in order, with the highest-percentile wave first.
- **FR-004**: System MUST define that access for a wave and all previous waves stays open from the wave's start until the general closing.
- **FR-005**: System MUST validate the period as described in the edge cases.
- **FR-006**: System MUST show the generated schedule to the Administrador and require confirmation before it is visible to Socios.
- **FR-007**: System MUST block regeneration once the first wave opened.
- **FR-008**: System MUST audit generation and confirmation.

### Key Entities

- **WaveSchedule**: event, segmentation, opening, closing, status (`draft` / `confirmed` / `invalidated`).
- **Wave**: as in HU-36, plus enablement date/time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of waves of a segmentation get an enablement date within the period.
- **SC-002**: Start dates are in percentile order and equally spaced (a parity test checks the formula).
- **SC-003**: 0 draft or invalidated schedules are visible to Socios.

## Assumptions

- "Equitable" means evenly spaced starts beginning at the opening, as in the formula above.
- Notifications of the schedule are outside the MVP (HU-19/20).
- A time zone is fixed (cross-cutting section 1).

## Revision Notes (v2)

- Defined the formula, validations, draft/confirm visibility, regeneration limits, and stated that access is informative in the MVP.
- v3: only for Partido events; empty waves omitted.

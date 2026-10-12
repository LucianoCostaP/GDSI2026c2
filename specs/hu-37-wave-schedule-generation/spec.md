# Feature Specification: Automatic Wave Schedule Generation

**Feature Branch**: `hu-37-wave-schedule-generation`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-37 (Estimate: 3, Priority: Alta, MVP: Yes)
**Input**: User description: "As a System Administrator, I want to automatically generate the enablement dates of each segmented wave, so that I define when reservation access opens for each group of Socios without assigning dates one by one."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic Wave Schedule Generation (Priority: P1)

As a System Administrator, I want to automatically generate the enablement dates of each segmented wave, so that I define when reservation access opens for each group of Socios without assigning dates one by one.

**Why this priority**: Turns the segmentation into a timeline that Socios can follow, avoiding manual per-wave configuration.

**Independent Test**: With an existing segmentation, define opening and closing dates and verify start dates are evenly distributed, highest percentile first.

**Acceptance Scenarios**:

1. **Given** an event without segmentation, **When** the Administrador tries to generate the schedule, **Then** it is not possible, as it requires an existing segmentation (HU-36).
2. **Given** an existing segmentation, **When** the Administrador defines the total reservation period: opening of the first wave and general closing date/time, **Then** the period is accepted.
3. **Given** a defined period, **When** the schedule is generated, **Then** start dates of each wave are distributed equitably within the period, in order, the highest-percentile wave enabling first.
4. **Given** a wave that reaches its start date/time, **When** it is enabled, **Then** access stays open for that wave and all previous ones until the reservation period closes.

---

### Edge Cases

- **Invalid period**: a closing date not after the opening date is rejected (inferred).
- **Regeneration**: generating again for the same segmentation replaces the previous schedule (to confirm).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST only generate a schedule over an existing segmentation.
- **FR-002**: System MUST let the Administrador define the total reservation period (first wave opening and general closing date/time).
- **FR-003**: System MUST distribute wave start dates equitably within the period, in order, with the highest-percentile wave first.
- **FR-004**: System MUST keep access open for a wave and all previous waves from the wave's start until the general closing.

### Key Entities

- **WaveSchedule**: event, reservation period (opening, closing).
- **Wave**: as in HU-36, plus enablement date/time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of waves of a segmentation get an enablement date within the reservation period.
- **SC-002**: Wave start dates are always in order of percentile (highest first) and equally spaced.

## Assumptions

- "Equitable" is interpreted as evenly spaced start times beginning at the opening of the first wave; the exact formula is fixed at planning.

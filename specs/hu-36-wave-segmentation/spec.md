# Feature Specification: Segment Socios into Waves

**Feature Branch**: `hu-36-wave-segmentation`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-36 (Estimate: 8, Priority: Alta, MVP: Yes)
**Input**: User description: "As a System Administrator, I want to automatically generate the segmentation of Socios into waves based on their ranking position, so that I establish the groups that will access turn reservation in a staggered way."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Segment Socios into Waves (Priority: P1)

As a System Administrator, I want to automatically generate the segmentation of Socios into waves based on their ranking position, so that I establish the groups that will access turn reservation in a staggered way.

**Why this priority**: Waves are how the club gives higher-ranked Socios earlier access; this is the mechanism that turns the ranking into actual priority.

**Independent Test**: For a published event with a calculated ranking, trigger segmentation and verify wave count, equal percentile bands, final wave grouping the remainder, and the per-wave output.

**Acceptance Scenarios**:

1. **Given** a published event, **When** the Administrador triggers segmentation generation for it, **Then** the process starts for that event.
2. **Given** the process, **When** it computes the number of waves, **Then** the count is derived automatically from the number of Socios enabled for the event and the real capacity (entries/seats), using a predefined rule.
3. **Given** the number of waves, **When** the ranking is divided, **Then** it is split into equal percentile bands according to that number.
4. **Given** the bands, **When** the last wave (lowest percentile) is defined, **Then** it acts as the final wave, grouping all Socios not included in earlier bands.
5. **Given** Abonados and Socios who received a seat by transfer, **When** segmentation is generated, **Then** they are excluded from the wave segmentation for that event.
6. **Given** a generated segmentation, **When** it is shown, **Then** it includes, per wave, its percentile range and the Socios that compose it.

---

### Edge Cases

- **Remainders**: Socios left over by uneven division fall in the final wave.
- **Unpublished event**: segmentation can only be generated for an already published event.
- **No calculated ranking**: segmentation requires a completed ranking (HU-25).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let the Administrador trigger segmentation for a specific published event.
- **FR-002**: System MUST compute the number of waves automatically from enabled Socios and real event capacity using a predefined rule.
- **FR-003**: System MUST divide the ranking into equal percentile bands according to the resulting number of waves.
- **FR-004**: System MUST make the last wave (lowest percentile) the final wave, grouping all Socios not included in earlier bands.
- **FR-005**: System MUST exclude Abonados and Socios with a transferred seat from the segmentation for that event.
- **FR-006**: System MUST include, per wave, the percentile range and its Socios.

### Key Entities

- **WaveSegmentation**: event, number of waves, generated at.
- **Wave**: order, percentile range, member Socios.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of non-excluded enabled Socios belong to exactly one wave.
- **SC-002**: The last wave contains all Socios not covered by earlier percentile bands.

## Assumptions

- The predefined rule for the number of waves, and how "Socios enabled for the event" is determined, are not defined in the backlog and must be fixed at planning.
- Event capacity is required here but is not captured by HU-21 (see README).
- The Abonado role no longer exists and seat transfer (HU-33) is not in the MVP, so the exclusion rule has no effect in the MVP; it is kept so the segmentation stays correct if those features return.

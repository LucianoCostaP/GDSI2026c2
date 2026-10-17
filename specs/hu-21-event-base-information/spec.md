# Feature Specification: Receive Event Base Information from the Club

**Feature Branch**: `hu-21-event-base-information`
**Revised**: 2026-10-16
**Status**: Draft
**Backlog Reference**: HU-21 (Estimate: 3, Priority: Alta, MVP: Yes).
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md)
**Contract**: [Club API contract](../../docs/club-api-contract.md)

## Direction and ownership

The club is the source of truth for event data and pushes events, changes, and cancellation notices to authenticated endpoints provided by the platform. The platform does not call, poll, or pull from a club API. The platform assigns an internal event ID and owns importance, publication, scoring configuration, and visibility. Club-owned fields are read-only to platform users.

## User Story 1 - Receive Event Base Information (Priority: P1)

As a System Administrator, I want the platform to receive upcoming and historical events pushed by the club so that they can be reviewed, published, or used for attendance history.

**Independent Test**: Have an authorized club client push a valid upcoming event, an invalid event, and a historical event. Verify the accepted event state, validation response, audit, and member visibility.

### Acceptance Scenarios

1. **Given** an authenticated club client, **When** it submits one or more valid upcoming events, **Then** each new event is created as `pending importance definition` with the club's external reference and original source data, and the platform records the receipt time.
2. **Given** an accepted pending event, **When** an Administrator views the event, **Then** the event is visible to administrators with its time remaining to the publication deadline, but not visible to members.
3. **Given** an event in `pending importance definition`, **When** the club pushes an update, **Then** valid source-field changes are applied without resetting the receipt time or publication window. If the update moves the start to less than 48 hours away, it is rejected, the existing event remains unchanged, and the Administrator is informed.
4. **Given** a pending event, **When** the club pushes a cancellation notice, **Then** the platform flags it and prevents automatic publication; the Administrator may discard it. Omission from a partial submission is not interpreted as cancellation.
5. **Given** an event whose start is less than 48 hours after receipt, **When** the club submits it for future publication, **Then** that item is rejected or reported as non-publishable with a reason; no incomplete event is created.
6. **Given** an event with missing or invalid date/time, venue, or type, **When** the club submits it, **Then** the API reports field-level validation errors and creates no incomplete record.
7. **Given** a retry with an external reference already stored, **When** the club resubmits it, **Then** no duplicate is created. Pending records may be updated under scenario 3; other lifecycle states return a conflict.
8. **Given** an authenticated historical import of events whose start has passed, **When** it is accepted, **Then** the events are stored as `historical`, are not published or visible to members, and can receive attendance records (HU-24). The Administrator assigns class/points in the historical import workflow.
9. **Given** a request without valid credentials, malformed request structure, or an unsupported type, **When** the platform receives it, **Then** it rejects the request without changing existing data. The platform does not make outbound API requests to the club.

## Event Data and Lifecycle

- Club-owned fields: external event reference, title, date/time, venue, type, and optional description.
- API field names: `id_externo`, `titulo`, `fecha_hora`, `lugar`, `tipo`, and optional `descripcion`. Wire values for `tipo` are `Partido` or `Institucional`; the platform may label the latter "Evento institucional/amateur" in product screens. The platform returns `id_interno` for later retrieval and updates.
- Platform-owned fields: internal ID, receipt time, lifecycle state, importance class/points, publication timestamps, and audit history.
- The club reference is unique and is used to correlate attendance submissions (HU-24).
- New future events start as `pending importance definition`; they are not visible to members until published under HU-22.
- Historical imports are stored as `historical`, never published, and remain available for attendance loading.
- PUT updates may change only `fecha_hora`, `lugar`, and `descripcion`; `titulo`, `tipo`, and `id_externo` are not editable through PUT. Pending updates do not reset the publication deadline. A club cancellation notice prevents automatic publication until administrator disposition.
- Event type is immutable after creation. A type mismatch on an update is rejected for administrator review.
- Events starting under 48 hours from receipt are not eligible for future publication. Historical imports are exempt.

## Functional Requirements

- **FR-001**: System MUST expose authenticated endpoints for club-initiated event submissions, updates, cancellation notices, and historical imports.
- **FR-002**: System MUST NOT call, poll, or pull event data from a club API.
- **FR-003**: System MUST validate each event and report rejected records and reasons; structurally invalid or unauthorized requests MUST NOT modify data.
- **FR-004**: System MUST create valid new future events as `pending importance definition` with source fields and receipt timestamp.
- **FR-005**: System MUST prevent duplicate events using the club external reference and update eligible pending events without resetting their publication deadline.
- **FR-006**: System MUST reject a pending update that would leave less than 48 hours before event start, preserving the existing record.
- **FR-007**: System MUST flag pending cancellations, prevent automatic publication, and permit administrator discard.
- **FR-008**: System MUST support historical event imports that are not published or visible to members but can receive attendance.
- **FR-009**: System MUST keep club-owned event data read-only to platform users and audit successful submissions, updates, rejections, cancellations, discards, and historical imports.

## Success Criteria

- **SC-001**: Every accepted future event begins in `pending importance definition` with its receipt timestamp recorded.
- **SC-002**: No pending, historical, or discarded event is visible to members.
- **SC-003**: No future event with less than 48 hours' lead is accepted for publication.
- **SC-004**: No external event reference produces duplicate platform records.
- **SC-005**: No platform-initiated outbound request to a club API occurs for event ingestion or refresh.

## Integration decisions

- HU-21's PDF describes POST, batch POST, GET, and PUT endpoints on the platform. The club initiates POST/PUT submissions; GET is a read operation available to the club and is not used by the platform to fetch club data.
- The supported routes and payloads are defined in the [Club API contract](../../docs/club-api-contract.md). PUT uses `/api/v1/eventos/{id_interno}` and edits only `fecha_hora`, `lugar`, and `descripcion`; title and type are not editable through PUT.
- The PDF does not define a historical-import route or cancellation signal. The contract proposes a separate historical route (TBD) and `POST /api/v1/eventos/{id_interno}/cancelacion`; confirm both with the club before implementation.
- Batch response details and retry/idempotency behavior follow the [Club API contract](../../docs/club-api-contract.md).

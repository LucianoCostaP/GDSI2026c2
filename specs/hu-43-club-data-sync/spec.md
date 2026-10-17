# Feature Specification: Receive Club Reference Data (new story)

**Feature Branch**: `hu-43-club-data-sync`
**Created**: 2026-10-12 | **Revised**: 2026-10-16 (push integration)
**Status**: Draft  
**Backlog Reference**: HU-43 (Estimate: 8, Priority: Alta, MVP: Yes).
**Shared rules**: [data contract](../_shared/data-contract.md), [cross-cutting](../_shared/cross-cutting.md)
**API contract**: [Club API contract](../../docs/club-api-contract.md)
**Input**: "As a platform, I need to receive an up-to-date, read-only copy of the club's Socio data through endpoints we provide, so identification, fee checks, scoring inputs and ranking eligibility use the club's source of truth."

## Direction and ownership

The club is the source of truth and pushes roster data to the platform's authenticated API. The platform does not call or pull data from a club API. The platform stores a read-only local copy; club-owned fields cannot be edited in the platform. The club sends a full initial snapshot and subsequent incremental changes, including additions, modifications, and removals.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Receive Socio Reference Data (Priority: P1)

**Independent Test**: Have a test club client push a full paged roster, then an incremental batch containing a new Socio, a changed fee status, and a removal. Verify the local copy, response/report, audit, and staleness indicator.

**Acceptance Scenarios**:

1. **Given** a club is authorized, **When** it pushes the initial full roster in pages, **Then** the platform stages the pages and activates a consistent snapshot for populations up to 500,000 Socios.
2. **Given** an active roster, **When** the club pushes incremental changes since its last successful delivery, **Then** valid additions, modifications, and removals are applied and summarized. If the club cannot provide a reliable delta, it can push a new full snapshot.
3. **Given** an Administrator starts an on-demand synchronization, **When** the request is submitted, **Then** the platform records the request and displays that it is waiting for a club push; the platform does not call the club's systems.
4. **Given** a full snapshot or incremental delivery completes, **When** it succeeds, **Then** the completion time and result are visible to the Administrator.
5. **Given** a delivery is structurally invalid, interrupted critically, or fails consistency checks, **When** it is rejected, **Then** the last good copy remains active, the failure is audited, and the Administrator is notified.
6. **Given** a record has duplicate DNI, missing/invalid birth date or alta date, or malformed email, **When** the club sends it, **Then** that record is rejected with a reason and other valid records are processed unless the load has a structural/critical failure.
7. **Given** a Socio's email or fee status changes, **When** that change is included in a successful club push, **Then** the local copy uses the new value. A Socio who regularizes fees is eligible at the next ranking calculation, keeping accumulated history.
8. **Given** the club reports a Socio baja, **When** the change is applied, **Then** that Socio leaves the eligible ranking population while their prior history remains.

### Edge Cases

- **Direction**: push only. The club initiates data delivery to the platform API; the platform does not read a club API.
- **Authentication**: every push uses the platform-issued club API key as a bearer token. The credential is stored as a secret and never appears in logs or errors.
- **Retries**: repeated delivery identifiers and pages are idempotent; conflicting content under the same identifier is rejected.
- **Contract changes**: request envelopes and records are validated against the agreed schema. Structural changes fail safely and preserve the last good copy.
- **Freshness**: if no successful roster update arrives within the configurable limit (24 hours by default), warn the Administrator before ranking calculation and wave segmentation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose authenticated endpoints for the club to push the Socio fields in the shared data contract.
- **FR-002**: System MUST support an initial complete paged snapshot and subsequent incremental batches of additions, modifications, and removals.
- **FR-003**: System MUST not activate a partial/corrupted full snapshot; the last good copy remains available until a new snapshot is complete and validated.
- **FR-004**: System MUST validate each record, report rejected records and reasons, and process valid records unless a structural or critical failure requires rejecting the operation.
- **FR-005**: System MUST record the latest received delivery's timestamp, status, and counts of created, updated, deactivated, and rejected Socios for administrators.
- **FR-006**: System MUST retain the read-only source copy and all Socio history, whatever the current fee status or active status.
- **FR-007**: System MUST audit successful, rejected, and failed deliveries without logging credentials.
- **FR-008**: System MUST warn when the last successful roster update is older than the configured freshness limit (24 hours by default) before HU-25 or HU-36.
- **FR-009**: System MUST meet the target of receiving up to 500,000 Socios in less than one hour and keep inconsistencies below 0.1%, subject to validation with the club.
- **FR-010**: System MUST support an Administrator-triggered resynchronization workflow that requests a club push; it MUST NOT fetch data from the club.

### Key Entities

- **SocioReference**: fields of the shared data contract, last synchronized at, active flag.
- **RosterLoad**: club, load ID, kind (`full` / `incremental`), started/received/completed at, status, counts, rejected-record report, pages received.

## Success Criteria *(mandatory)*

- **SC-001**: After successful snapshot activation or incremental application, the local copy matches all valid records in that delivery.
- **SC-002**: A structurally or critically failed delivery changes no active roster data.
- **SC-003**: Inconsistency between the delivered data and the local copy is below 0.1% after a successful run.
- **SC-004**: A full snapshot of up to 500,000 Socios is received and processed within one hour, subject to validation with the club.
- **SC-005**: No roster synchronization operation initiated by the platform makes an outbound request to the club.

## Assumptions and integration decisions

- The club can push a full initial snapshot and incremental changes, including removals. The club and platform agree on stable external IDs, page/chunk envelope, completion semantics, delta watermarks, and retry identifiers.
- Field names, load paths, response reports, and validation rules follow the [Club API contract](../../docs/club-api-contract.md); incremental records use `id_externo` and `fecha_modificacion`.
- An Administrator-triggered resynchronization is an internal request/notification for the club to push again; it does not cause an outbound API call by the platform.
- The same platform API credential may authorize the club's event and participation pushes (HU-21 and HU-24), subject to the agreed scope model.
- Distance to the stadium is included or provided as an agreed precomputed field; the platform does not geocode addresses or store exact home addresses.
- If the club cannot provide incremental history, it sends a fresh full snapshot.

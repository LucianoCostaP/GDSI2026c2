# Feature Specification: Receive Attendance and Recurring Activities from the Club

**Feature Branch**: `hu-24-attendance-load`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3.3)
**Status**: Draft
**Backlog Reference**: HU-24 (Estimate: 5, Priority: Alta, MVP: Yes). Re-estimate: second data kind (recurring activities), club push endpoints and file fallback. Needed by HU-25: without it no attendance or participation enters the system.
**Shared rules**: [data contract](../_shared/data-contract.md), [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a System Administrator, I want to load the list of Socios who attended an event, or who took part in a recurring institutional activity, from the club's data, so that the system can calculate the impact of that participation on each Socio's scoring."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Load Attendance and Recurring Activities (Priority: P1)

As a System Administrator, I want the platform to receive attendance and recurring activity data pushed by the club, so that the system can calculate the impact of that participation on each Socio's scoring. The Administrator can use a CSV file with the same data as a fallback.

**Why this priority**: Attendance and participation are the main inputs to the ranking. Both kinds share the same loading mechanism (validation, tolerance, error report, audit), so they live in one story. The Socio data is pushed through the platform API in HU-N2.

**Independent Test**: Have a test club client push attendance for a played event and recurring activities, verify the confirmation with loaded and rejected counts; submit an invalid/failed delivery and verify nothing is persisted and the file fallback works.

**Acceptance Scenarios**:

1. **Given** an authenticated club client, **When** it pushes attendance for an eligible event (identified by the club event reference stored at import) or recurring activities, **Then** the platform validates the delivery and makes its result available to the Administrator.
2. **Given** an Administrator opens the load screen, **When** club data has been received, **Then** they can review the counts and apply/confirm the load, or choose a CSV file as the fallback source.
3. **Given** the club pushes recurring activities, **When** the delivery is processed, **Then** it includes changes since the last successful delivery (or, on first delivery, the last 365 days) and is validated before processing.
4. **Given** a club push is unauthorized, structurally invalid, or critically interrupted, **When** the platform receives it, **Then** no partial data is persisted and an error is shown to the Administrator; the CSV file is offered as an alternative. The platform does not call a club API.
5. **Given** the club submits an empty attendance set for a past event, **When** the delivery is processed, **Then** nothing is interpreted as "nobody attended" or used to replace existing records; the reason is shown, and the Administrador can use the CSV file.
6. **Given** a CSV file as source, **When** it has a structural problem (not UTF-8 CSV, missing header or required column, empty, too large, or for attendance a `fecha_evento` that differs from the selected event's date), **Then** an error is shown and nothing is processed or persisted.
7. **Given** data from either source, **When** it is processed, **Then** each row is validated (see Edge Cases) and the system confirms how many records were loaded (and, for activities, updated) and how many were rejected, with a downloadable list of rejected rows and the reason.
8. **Given** more than 5% of rows are rejected, **When** processing, **Then** the whole load is rejected and nothing is persisted.
9. **Given** an event that already has an attendance load, **When** a new load is requested for it, **Then** the system informs that a previous load exists (date, who, source, records) and asks for confirmation before replacing it; on confirmation the replacement is atomic and the previous load is kept as history.
10. **Given** the Administrador declines the replacement, **When** they cancel, **Then** the previous load stays unchanged.
11. **Given** an activity record already loaded (same `dni`, `tipo`, `fecha_desde`), **When** it appears again, **Then** it is updated, not duplicated, and counted as updated.
12. **Given** loaded attendance or activity data, **When** the ranking calculation (HU-25) runs, **Then** the data is available to it.
13. **Given** a load or replacement completed after the latest ranking, **When** the Administrador views the ranking status, **Then** a notice says the ranking is older than the loaded data.

---

### Edge Cases

- **Attendance, eligible events**: `published` or `historical` events whose start has already passed. Future events are not selectable. Both event types are eligible: attendance at a Partido feeds the attendance pillar and attendance at an Evento institucional/amateur (elections and assemblies included) feeds the institutional pillar with the points defined for that event.
- **Event matching in club submissions**: by the club event reference that HU-21 stores for every imported event.
- **Attendance rows**: identified by DNI. Socios not in the club data are rejected, and so is a `numero_socio` that does not match the DNI. A DNI repeated in the data is rejected as a duplicate.
- **Activity rows**: `tipo` must be `deporte_federado` or `subcomision`; `fecha_desde` and `fecha_hasta` are required, `fecha_hasta` is on or after `fecha_desde`, and neither is in the future. Socios not in the club data are rejected.
- **Overdue fees**: Socios with overdue fees are accepted: their history is kept.
- **Partial validity**: only correctly loaded rows are counted in the confirmation (within the tolerance).
- **Volume**: submissions are paged/chunked; one event can bring tens of thousands of rows.
- **Credentials**: club credentials for pushing to platform endpoints are secrets, may be scoped by data type, and never appear in logs.
- **Triggers**: loads start when the Administrador asks; scheduled loads are outside the MVP.
- **Corrections of activities**: loading the corrected record updates it; deleting records is not supported in the MVP.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose authenticated endpoints for the club to push attendance and recurring activities, and let the Administrador choose received club data or CSV file for loading.
- **FR-002**: System MUST NOT request or pull attendance or activity data from a club API.
- **FR-003**: System MUST validate the structure of the club push or file first and the rows second.
- **FR-004**: System MUST persist nothing when the source fails, the structure is invalid, the result is empty or ambiguous, or row errors exceed the tolerance.
- **FR-005**: System MUST confirm the numbers of records loaded, updated and rejected and provide the rejected rows with reasons.
- **FR-006**: System MUST make the loaded data available to the scoring engine and record its source (`club_push` or `file`).
- **FR-007**: System MUST warn about an existing attendance load and require confirmation before an atomic replacement, keeping the previous load as history.
- **FR-008**: System MUST load activity records idempotently (upsert by `dni`, `tipo`, `fecha_desde`).
- **FR-009**: System MUST show that the ranking is stale after a load.
- **FR-010**: System MUST audit every load and replacement.

### Key Entities

- **ParticipationLoad**: kind (`attendance` / `activities`), source (`club_push` / `file`), event (attendance only), loaded by, loaded at, records loaded, updated and rejected, status (`active` / `replaced`).
- **AttendanceRecord**: Socio and event attended.
- **ActivityRecord**: Socio, type (`deporte_federado` / `subcomision`), from date, to date.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of failed, empty, ambiguous, structurally invalid or over-tolerance loads persist nothing.
- **SC-002**: 100% of attendance replacements require explicit confirmation and are atomic.
- **SC-003**: Every rejected row is reported with a reason.
- **SC-004**: Loading the same activities twice creates 0 duplicates.
- **SC-005**: The activities and attendance of the reference dataset contribute exactly the points of the scoring model.

## Assumptions

- The club pushes attendance (by event reference) and recurring activities (by modification date), besides the Socio data of HU-N2 and the events of HU-21.
- The CSV file keeps the same data as the club push schema (data contract, sections 3 and 4) and serves as fallback.
- Elections and assemblies are events, not activities, and use the attendance kind.
- Recalculation after a load is a manual decision (HU-25); the stale-ranking notice is the only automatic effect.
- The backlog wording of HU-24 mentions a file and attendance only; it should be extended to platform endpoints for club pushes and recurring activities.

## Revision Notes

- v2: defined format, eligibility, row versus file validation, tolerance, error report, atomic replacement and stale-ranking notice.
- v3: format confirmed as CSV; added `fecha_evento` and `numero_socio` checks; both event types are eligible.
- v3.2: recurring activities moved here from the former HU-N1, which is removed.
- v3.4: events carry the club reference, so attendance submissions identify the event by that reference; the ambiguous-match case is gone.
- v3.4: the primary source is a club push to platform-provided endpoints; the CSV file is the fallback; platform-initiated club API pulls are out of scope.

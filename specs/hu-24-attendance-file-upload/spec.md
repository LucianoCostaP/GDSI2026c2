# Feature Specification: Load Attendance by File

**Feature Branch**: `hu-24-attendance-file-upload`
**Created**: 2026-10-11 | **Revised**: 2026-10-12 (v2)
**Status**: Draft
**Backlog Reference**: HU-24 (Estimate: 5, Priority: Alta, MVP: Yes). Needed by HU-25: without it no attendance enters the system.
**Shared rules**: [data contract](../_shared/data-contract.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a System Administrator, I want to upload a file with the list of Socios who attended an event, so that the system can calculate the impact of that attendance on each Socio's scoring."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Load Attendance by File (Priority: P1)

As a System Administrator, I want to upload a file with the list of Socios who attended an event, so that the system can calculate the impact of that attendance on each Socio's scoring.

**Why this priority**: Attendance is the main input to the ranking.

**Independent Test**: Upload a valid file for an event and verify the confirmation with loaded and rejected counts; upload a file with a bad structure and verify nothing is persisted.

**Acceptance Scenarios**:

1. **Given** an Administrador logged in, **When** they select an eligible event and upload the attendance file, **Then** the system validates the file before processing.
2. **Given** a file with a structural problem (not UTF-8 CSV, missing header or `dni` column, empty, too large), **When** it is uploaded, **Then** an error is shown and nothing is processed or persisted.
3. **Given** a structurally valid file, **When** it is processed, **Then** each row is validated (DNI format, existing Socio, no duplicate DNI in the file) and the system confirms how many records were loaded and how many were rejected, with a downloadable list of rejected rows and the reason.
4. **Given** more than 5% of rows are rejected, **When** processing, **Then** the whole file is rejected and nothing is persisted. [NEEDS CLARIFICATION: confirm the 5% tolerance.]
5. **Given** loaded attendance data, **When** the ranking calculation (HU-25) runs, **Then** the data is available to it.
6. **Given** an event that already has a load, **When** a new file is uploaded for it, **Then** the system informs that a previous load exists (date, who, records) and asks for confirmation before replacing it; on confirmation the replacement is atomic and the previous load is kept as history.
7. **Given** the Administrador declines the replacement, **When** they cancel, **Then** the previous load stays unchanged.
8. **Given** a load or replacement completed after the latest ranking, **When** the Administrador views the ranking status, **Then** a notice says the ranking is older than the attendance data.

---

### Edge Cases

- **Eligible events**: `published` or `historical` events whose start has already passed. Future events are not selectable.
- **Identification**: by DNI. Socios not in the club data are rejected as rows.
- **Partial validity**: only correctly loaded rows are counted in the confirmation (within the tolerance).
- **Declined replacement**: the previous load is kept.
- **Format**: defined in the data contract. [NEEDS CLARIFICATION: confirm against the real export of the stadium.]

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let the Administrador select an eligible event and upload an attendance file.
- **FR-002**: System MUST validate structure first and rows second.
- **FR-003**: System MUST reject the file with an error, persisting nothing, on a structural problem or when row errors exceed the tolerance.
- **FR-004**: System MUST confirm the numbers of records loaded and rejected and provide the rejected rows with reasons.
- **FR-005**: System MUST make the loaded attendance data available to the scoring engine.
- **FR-006**: System MUST warn about an existing load and require confirmation before an atomic replacement, keeping the previous load as history.
- **FR-007**: System MUST show that the ranking is stale after a load.
- **FR-008**: System MUST audit every load and replacement.

### Key Entities

- **AttendanceLoad**: event, file name, loaded by, loaded at, records loaded, records rejected, status (`active` / `replaced`).
- **AttendanceRecord**: Socio and event attended.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of structurally invalid files and files above the tolerance are rejected with nothing persisted.
- **SC-002**: 100% of replacements require explicit confirmation and are atomic.
- **SC-003**: Every rejected row is reported with a reason.

## Assumptions

- This story is required by the MVP chain even though other documents may rank it lower.
- Recalculation after a load is a manual decision (HU-25); the stale-ranking notice is the only automatic effect.

## Revision Notes (v2)

- Defined format, eligibility, row versus file validation, tolerance, error report, atomic replacement and stale-ranking notice.

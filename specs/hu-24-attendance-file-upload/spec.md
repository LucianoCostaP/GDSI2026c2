# Feature Specification: Load Attendance by File

**Feature Branch**: `hu-24-attendance-file-upload`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-24 (Estimate: 5, Priority: Alta, MVP: Yes)
**Input**: User description: "As a System Administrator, I want to upload a file with the list of Socios who attended an event, so that the system can calculate the impact of that attendance on each Socio's scoring."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Load Attendance by File (Priority: P1)

As a System Administrator, I want to upload a file with the list of Socios who attended an event, so that the system can calculate the impact of that attendance on each Socio's scoring.

**Why this priority**: Attendance is the main input to the ranking; without it the ranking cannot reflect real behavior.

**Independent Test**: Upload a valid attendance file for an event and verify the confirmation with the number of records loaded; then upload an invalid file and verify nothing is processed.

**Acceptance Scenarios**:

1. **Given** an Administrador logged in, **When** they select an event and upload the attendance file, **Then** the system validates the file format before processing it.
2. **Given** a file that does not meet the expected format, **When** it is uploaded, **Then** an error is shown and the load is not processed.
3. **Given** a valid file, **When** it is processed, **Then** the system confirms how many attendance records were loaded correctly.
4. **Given** loaded attendance data, **When** the scoring engine (HU-25) runs, **Then** the data is available to it.
5. **Given** an event that already has a previous attendance load, **When** a new file is uploaded for the same event, **Then** the system informs that a previous load exists and asks for confirmation before replacing it.

---

### Edge Cases

- **Partial validity**: only records loaded correctly are counted in the confirmation.
- **Declined replacement**: if the Administrador does not confirm, the previous load is kept unchanged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let the Administrador select an event and upload an attendance file.
- **FR-002**: System MUST validate the file format before processing.
- **FR-003**: System MUST reject the file with an error, processing nothing, when the format is not as expected.
- **FR-004**: System MUST confirm the number of attendance records loaded correctly.
- **FR-005**: System MUST make the loaded attendance data available to the scoring engine.
- **FR-006**: System MUST warn about an existing load for the same event and ask for confirmation before replacing it.

### Key Entities

- **AttendanceLoad**: event, uploaded file, loaded-at, records loaded.
- **AttendanceRecord**: Socio and event attended.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of files with an invalid format are rejected with nothing persisted.
- **SC-002**: 100% of replacements require explicit confirmation.

## Assumptions

- The expected file format (e.g. CSV and its columns) is not defined in the backlog and is fixed at planning.
- When the ranking is recalculated after a load is defined by HU-25, not here.

# Feature Specification: Club Reference Data Synchronization (new story)

**Feature Branch**: `hu-n2-club-data-sync`
**Created**: 2026-10-12 | **Revised**: 2026-10-13 (v3)
**Status**: Draft. **New technical story, to be added to the backlog** (provisional id HU-N2; estimate to be defined).
**Shared rules**: [data contract](../_shared/data-contract.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As the system, I need an up-to-date, read-only copy of the club's Socio data, obtained from the club API, so that identification, fee checks, scoring inputs and ranking eligibility use the club's source of truth."

**Why this story exists**: HU-01, HU-05, HU-14, HU-25 and HU-36 rely on Socio data (DNI, member number, email, birth date, alta date, previous baja, fee status, distance) that the system does not create. The club provides it through an API.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Synchronize Socio Reference Data (Priority: P1)

**Independent Test**: Run a synchronization against a test API with one new Socio, one changed fee status and one removed Socio, and verify the copy, the audit and the staleness indicator.

**Acceptance Scenarios**:

1. **Given** the club API, **When** the first synchronization runs, **Then** a full load copies every Socio (up to 500,000) page by page.
2. **Given** a completed first load, **When** later synchronizations run (scheduled and on demand by an Administrador), **Then** only records changed since the last successful run are requested and the local read-only copy is updated for new, changed and removed Socios.
3. **Given** a synchronization finishes, **When** it succeeds, **Then** the time of the last successful synchronization is recorded and shown to the Administrador.
4. **Given** the API is unavailable, times out or returns invalid data, **When** a synchronization fails, **Then** it retries with increasing waits, the last good copy stays in use, the failure is recorded and the Administrador is notified on screen.
5. **Given** the copy is older than the staleness limit (default 24 hours), **When** HU-25 starts, **Then** it warns the Administrador (stated in that spec).
6. **Given** a record that breaks the contract (duplicate DNI, missing birth date or alta date, invalid email), **When** synchronizing, **Then** the record is rejected and listed in the synchronization report, and the others load.
7. **Given** a Socio with a changed email or fee status, **When** synchronized, **Then** later logins and checks use the new value.

---

### Edge Cases

- **Direction**: read-only. The system never writes to the club API.
- **Fee status changes** to overdue or back to up to date are applied at the next synchronization; a Socio who pays up returns to the ranking at the next calculation with their accumulated history.
- **Removed Socios** are marked inactive and leave the ranking population; their history is kept.
- **Authentication**: the API credential is stored as a secret and never appears in logs.
- **Contract changes**: the API response is validated against an expected schema; an unexpected change fails the run instead of loading bad data.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST maintain a read-only copy of the Socio fields in the data contract, taken from the club API.
- **FR-002**: System MUST run a full first load and then incremental loads, paginated.
- **FR-003**: System MUST synchronize on a schedule and on demand.
- **FR-004**: System MUST validate each record against the contract and report rejected ones.
- **FR-005**: System MUST keep the last good copy on failure, retry, and record the failure.
- **FR-006**: System MUST expose the last successful synchronization time.
- **FR-007**: System MUST audit synchronizations (counts of new, changed, removed, rejected).
- **FR-008**: System MUST keep every Socio's history, whatever their fee status.

### Key Entities

- **SocioReference**: fields of the data contract, last synchronized at, active flag.
- **SyncRun**: started at, ended at, status, counts, errors.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a successful run the copy matches the API for all valid records.
- **SC-002**: A failed run changes no data.
- **SC-003**: Inconsistency between the copy and the API is below 0.1% after a run.
- **SC-004**: An incremental run for the usual daily changes finishes in minutes, and the full first load of 500,000 Socios finishes within one hour. [targets to validate against the real API]

## Assumptions

- The same API client and credential are used by HU-24 for attendance and recurring activities.
- The club API supports pagination and filtering by modification date. If it does not, the system falls back to full loads.
- Distance to the stadium is provided by the club (or precomputed once); the system does not geocode addresses and does not store home addresses.

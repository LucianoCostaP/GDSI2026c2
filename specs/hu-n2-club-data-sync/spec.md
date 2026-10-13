# Feature Specification: Club Reference Data Synchronization (new story)

**Feature Branch**: `hu-n2-club-data-sync`
**Created**: 2026-10-12
**Status**: Draft. **New technical story, to be added to the backlog** (provisional id HU-N2; estimate to be defined).
**Shared rules**: [data contract](../_shared/data-contract.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As the system, I need an up-to-date, read-only copy of the club's Socio data, so that identification, fee checks, scoring inputs and wave segmentation use the club's source of truth."

**Why this story exists**: HU-01, HU-05, HU-14, HU-25 and HU-36 rely on Socio data (DNI, member number, email, birth date, alta date, previous baja, fee status, distance) that the system does not create. No story says how it arrives.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Synchronize Socio Reference Data (Priority: P1)

**Independent Test**: Run a synchronization against a test source with one new Socio, one changed fee status and one removed Socio, and verify the copy, the audit and the staleness indicator.

**Acceptance Scenarios**:

1. **Given** the club data source, **When** a synchronization runs (scheduled and on demand by an Administrador), **Then** the local read-only copy is updated for new, changed and removed Socios.
2. **Given** a synchronization finishes, **When** it succeeds, **Then** the time of the last successful synchronization is recorded and shown to the Administrador.
3. **Given** the source is unavailable or returns invalid data, **When** a synchronization fails, **Then** the last good copy stays in use, the failure is recorded and the Administrador is notified on screen.
4. **Given** the copy is older than the staleness limit (default 24 hours), **When** HU-25 or HU-36 starts, **Then** they warn the Administrador (stated in those specs).
5. **Given** a record that breaks the contract (duplicate DNI, missing birth date or alta date, invalid email), **When** synchronizing, **Then** the record is rejected and listed in the synchronization report, and the others load.
6. **Given** a Socio with a changed email or fee status, **When** synchronized, **Then** later logins and checks use the new value.

---

### Edge Cases

- **Direction**: read-only. The system never writes to the club source.
- **Removed Socios** are marked inactive and leave the ranking population; their history is kept.
- **Mode**: API or periodic snapshot file. [NEEDS CLARIFICATION: which one the club provides.]

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST maintain a read-only copy of the Socio fields in the data contract.
- **FR-002**: System MUST synchronize on a schedule and on demand.
- **FR-003**: System MUST validate each record and report rejected ones.
- **FR-004**: System MUST keep the last good copy on failure and record the failure.
- **FR-005**: System MUST expose the last successful synchronization time.
- **FR-006**: System MUST audit synchronizations (counts of new, changed, removed, rejected).

### Key Entities

- **SocioReference**: fields of the data contract, last synchronized at, active flag.
- **SyncRun**: started at, ended at, status, counts, errors.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a successful run the copy matches the source for all valid records.
- **SC-002**: A failed run changes no data.
- **SC-003**: Inconsistency between the copy and the source is below 0.1% after a run.

## Assumptions

- Distance to the stadium is provided by the club (or precomputed once); the system does not geocode addresses and does not store home addresses.

# Feature Specification: Load Institutional Participation by File (new story)

**Feature Branch**: `hu-n1-institutional-participation-load`
**Created**: 2026-10-12
**Status**: Draft. **New story, to be added to the backlog** (provisional id HU-N1; estimate to be defined by the team, comparable to HU-24).
**Shared rules**: [scoring model](../_shared/scoring-model.md), [data contract](../_shared/data-contract.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a System Administrator, I want to upload a file with the institutional participation of Socios (elections, assemblies, federated sport, subcommissions), so that the institutional participation pillar of the score reflects it."

**Why this story exists**: the scoring model includes a participation pillar (20% of the default weight) and the MVP keeps it. No other story brings that data into the system; without this story the pillar would be 0 for everyone.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Load Institutional Participation by File (Priority: P1)

As a System Administrator, I want to upload a file with the institutional participation of Socios, so that the participation pillar of the score reflects it.

**Independent Test**: Upload a valid file with an assembly and a federated-sport range for a Socio, run HU-25 and verify the institutional component equals 40 + 10 × months, capped by the configured limit.

**Acceptance Scenarios**:

1. **Given** an Administrador logged in, **When** they upload a CSV with columns `dni`, `tipo`, `fecha_desde`, `fecha_hasta`, **Then** the system validates the structure first and the rows second.
2. **Given** a structural problem (encoding, header, columns, empty file), **When** uploaded, **Then** an error is shown and nothing is persisted.
3. **Given** a valid file, **When** processed, **Then** the system confirms records loaded, updated and rejected, with a downloadable list of rejected rows and reasons.
4. **Given** more than 5% of rows rejected, **When** processing, **Then** the whole file is rejected and nothing is persisted.
5. **Given** a record already loaded (same `dni`, `tipo`, `fecha_desde`), **When** it appears again, **Then** it is updated, not duplicated, and counted as updated.
6. **Given** a `tipo` that is `eleccion` or `asamblea`, **When** the row is validated, **Then** it needs `fecha_desde` and an empty `fecha_hasta`; for `deporte_federado` and `subcomision` it needs both dates with `fecha_hasta` on or after `fecha_desde`.
7. **Given** loaded data, **When** HU-25 runs, **Then** it counts only civic events dated within 365 days before the calculation date and the months of activities inside that period (at most 12 per activity).

---

### Edge Cases

- **Point values** are constants of the scoring model: election 50, assembly 40, federated sport 10 per month, subcommission 15 per month. The cap is the editable `Pinst_max`.
- **Unknown Socio**: the row is rejected.
- **Future dates** are rejected.
- **Correction**: loading the corrected row updates it; deleting records is not supported in the MVP.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a CSV of participation records as defined in the data contract.
- **FR-002**: System MUST validate structure, then rows, and reject the file above the tolerance.
- **FR-003**: System MUST load valid rows idempotently (upsert by `dni`, `tipo`, `fecha_desde`).
- **FR-004**: System MUST confirm loaded, updated and rejected counts and provide rejected rows with reasons.
- **FR-005**: System MUST make the data available to the ranking calculation with the 365-day moving window.
- **FR-006**: System MUST show that the ranking is stale after a load.
- **FR-007**: System MUST audit every load.

### Key Entities

- **ParticipationLoad**: file, loaded by, loaded at, counts.
- **ParticipationRecord**: Socio, type, from date, to date.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of structurally invalid files are rejected with nothing persisted.
- **SC-002**: Re-uploading the same file creates 0 duplicates.
- **SC-003**: The institutional component of the reference dataset matches the scoring model.

## Assumptions

- The club exports these records from its own records; the file format may need to be adapted to that export. [NEEDS CLARIFICATION]
- A single institutional participation per `tipo` and date is enough for the model (`Ak` is 0 or 1).

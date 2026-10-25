# Feature Specification: Receive and Update the Socio Roster Sent by the Club

**Feature Branch**: `hu-43-club-roster-reception`
**Created**: 2026-10-12 | **Revised**: 2026-10-25 (v4)
**Status**: Draft
**Backlog Reference**: HU-43 (Estimate: 8, Priority: Alta, MVP: Yes). Replaces the provisional HU-N2.
**Shared rules**: [data contract](../_shared/data-contract.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an Admin, I want the system to offer an integration interface (API/endpoints) to receive from the club the initial roster and the updates to the Socios' data, so that it keeps an up-to-date, read-only local copy that serves as the source of truth for identification, fee checks, scoring inputs and ranking eligibility."

**Why this story exists**: HU-01, HU-05, HU-14, HU-25 and HU-36 rely on Socio data (DNI, member number, email, birth date, alta date, previous baja, fee status, distance) that the system does not create. The club **sends** it to the system through endpoints the system exposes. The system never calls an API of the club.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Receive the Socio Roster from the Club (Priority: P1)

**Independent Test**: With a club token, send a full load in two pages, then an incremental batch with one alta, one changed fee status and one baja. Verify the copy, the counts, the rejected records with their reasons, the idempotent resend and the staleness indicator.

**Acceptance Scenarios**:

1. **Given** the club has a valid integration token, **When** it sends a **full load** as numbered pages (`carga_id`, `pagina`, `total_paginas`), **Then** each page is received and staged (`202 Accepted`, load state `receiving`), and nothing changes in the copy until the last page arrives. Up to 500,000 Socios are supported.
2. **Given** the last page of a full load arrives, **When** the final consistency check passes (no DNI or `id_externo` repeated across pages), **Then** the snapshot is activated atomically: Socios in the snapshot are created or updated, Socios of the copy that are absent from it are marked inactive (baja), and the load ends `successful`.
3. **Given** the final consistency check finds a DNI or `id_externo` repeated across pages, **When** the last page arrives, **Then** the whole load ends `failed` (`422 CONSISTENCY_CHECK_FAILED`), no change is applied, the last valid copy stays in use, and the load accepts no more pages.
4. **Given** a first full load exists, **When** the club sends an **incremental batch** (`lote_id`, `desde`, `hasta`, and a list of changes with action `alta`, `modificacion` or `baja`), **Then** each valid change is applied immediately, even if other changes of the same batch are rejected, and the response returns the counts created, updated, deactivated and rejected.
5. **Given** any record sent by the club, **When** it is validated, **Then** a record with a duplicate DNI, a missing or invalid birth date or alta date, an invalid email format, or any other field outside the contract is **rejected individually**; the rest are processed normally; and the response and the load record list each rejection with `id_externo`, `field`, `codigo` and `motivo`.
6. **Given** a request whose structure breaks the contract (not JSON, missing `carga_id`/`lote_id`, a page number above `total_paginas`, a page or total that conflicts with the existing load), **When** it is received, **Then** it is rejected as a whole with the error format of the data contract and nothing is applied.
7. **Given** a page or a batch that was already received, **When** the club sends it again with the same content, **Then** the original result is returned and nothing is applied twice. **When** it is sent again with different content, **Then** it is rejected with `409 CONFLICT`.
8. **Given** a change in the email or the fee status of a Socio, **When** it is applied, **Then** later logins (HU-05), activations (HU-01) and the next ranking (HU-25) use the new value. A Socio who pays up returns to the population of the next ranking with their accumulated history.
9. **Given** a baja (an incremental `baja`, or a Socio absent from a full load), **When** it is applied, **Then** the Socio is marked inactive, leaves the population of the next ranking and keeps their attendance and score history. Nothing is deleted.
10. **Given** a completed load, **When** the Admin opens the reception status, **Then** they see the date, time and result of the latest load received from the club and its counts (created, updated, deactivated, rejected), and can open the rejected records with their reasons.
11. **Given** more than 24 hours (configurable) without a successful load, **When** the Admin starts the ranking calculation (HU-25) or the wave segmentation (HU-36), **Then** they are warned that the local copy exceeds the recommended age.
12. **Given** a request without a token, with a malformed `Authorization` header, or with an unknown or inactive token, **When** it is received, **Then** it is rejected with `401 UNAUTHORIZED`, nothing is changed, and neither the token nor personal data appear in the logs or in the error message.
13. **Given** the copy received from the club, **When** anyone uses the platform, **Then** no screen or endpoint allows editing it manually.

---

### Edge Cases

- **Direction**: the club calls the system. The system exposes the endpoints and never calls the club.
- **Club status query**: the club can ask for the state and rejections of any of its loads and for the freshness of its copy (data contract, section 5).
- **Fee status changes** to overdue or back to up to date apply when received.
- **Socio data fields**: exactly the ones in the data contract, section 1. Exact home addresses are never received or stored; distance comes already calculated by the club, and the locality is optional.
- **Contract changes**: payloads are validated against the expected schema; a structural change fails the request instead of loading bad data.
- **Interrupted full load**: "critically interrupted" means a full load whose pages are not all received within 60 minutes of its first page. It ends `failed` (`LOAD_EXPIRED`), its staged records are discarded, the last valid copy stays in use and it accepts no more pages; the club starts again with a new `carga_id`.
- **Reliable incremental batch**: a batch is reliable when a successful full load exists and its `desde` is not later than the `hasta` of the last successful batch (or the completion of the last full load), so no change can fall in a gap. Otherwise it is rejected whole (`WATERMARK_GAP`) and the club resends from the last watermark or sends a full load. `desde` and `hasta` carry explicit time zone offsets.
- **Size limits**: up to 10,000 records per page or batch (data contract, section 5).
- **Baja of a Socio with an account**: the account keeps its state, but the Socio can no longer activate (HU-01) or log in (HU-05), and every open session of that Socio is revoked when the baja is applied. If the club sends the Socio again (alta), access and history return.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose authenticated endpoints for a paginated full load and for incremental batches of altas, modificaciones and bajas.
- **FR-002**: System MUST stage a full load and activate it atomically only when every page has arrived and the cross-page consistency check passes; otherwise it MUST keep the last valid copy.
- **FR-003**: System MUST validate each record individually, apply the valid ones, and report every rejected record with `id_externo`, `field`, `codigo` and `motivo`, both in the response and in the stored load.
- **FR-004**: System MUST reject a structurally invalid request as a whole, without partial changes.
- **FR-005**: System MUST be idempotent by `carga_id` + page and by `lote_id` (same content returns the original result; different content returns `409`).
- **FR-006**: System MUST keep the copy read-only and mark bajas as inactive without deleting history.
- **FR-007**: System MUST show the Admin the date, time, result and counts of the latest load, and its rejected records.
- **FR-008**: System MUST warn before HU-25 and HU-36 when the latest successful load is older than the staleness limit (default 24 hours).
- **FR-009**: System MUST authenticate the club by a Bearer token, shared with HU-21 and HU-24, stored hashed and never written to logs or error messages.
- **FR-010**: System MUST audit every load (who, when, counts, result).
- **FR-011**: System MUST revoke the sessions of a Socio when their baja is applied and refuse their activation and login while they are inactive.

### Key Entities

- **Socio**: fields of the data contract, active flag, last modified at (from the club), created and updated at.
- **SocioLoad**: `carga_id` / `lote_id`, kind (`full` / `incremental`), state (`receiving` / `processing` / `successful` / `failed`), pages expected and received, watermarks, counts (total, created, updated, deactivated, rejected), payload hash, error message, started and completed at.
- **SocioLoadRejection**: load, `id_externo`, field, code, reason.
- **ClubIntegrationToken**: club, token hash, active flag.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a successful load the copy matches what the club sent for all valid records.
- **SC-002**: A failed or structurally invalid load changes no data.
- **SC-003**: Processing discrepancies stay below 0.1% after a load.
- **SC-004**: The full initial load of up to 500,000 Socios is processed in under one hour. [target to validate with a load test]
- **SC-005**: Sending the same page or batch twice creates 0 duplicates.

## Assumptions

- The club can call an HTTPS endpoint with a Bearer token and paginate its full load.
- Distance to the stadium is calculated by the club; the system does not geocode and does not store home addresses.
- The club sends a full load first and incremental batches afterwards, at least once every 24 hours.

## Implementation Status (prototype `gdsi-api-carga-socios`)

Already implemented, and the source of the contract above:

- `POST /api/v1/socios/cargas/completa` (paged snapshot with staging and atomic activation on the last page; cross-page duplicate check fails the whole load), `POST /api/v1/socios/cargas/incremental` (per-record rejection; valid changes applied), `GET /api/v1/socios/cargas/{carga_id}` (state, counts, rejections), `GET /api/v1/socios/freshness` (24-hour limit), `GET /api/v1/socios` (paginated query of the copy).
- Rejection codes: `INVALID_RECORD_FORMAT`, `DUPLICATE_DNI_PAGE`, `DUPLICATE_ID_EXTERNO_PAGE`, `DUPLICATE_DNI_ACROSS_PAGES`, `INVALID_SOCIO_DATA`, `MISSING_SOCIO_DATA`, `DUPLICATE_DNI`, `SOCIO_NOT_FOUND`, `MISSING_ID_EXTERNO`.
- Idempotency by payload hash with `409 CONFLICT` on different content; error body `{"error": {"code", "message", "field"}}`.
- Multi-tenant by club: Bearer token per club and Postgres views filtered by `app.current_club_id`.

Gaps to close when porting it to this backend:

- Club tokens are stored in plain text (`clubes.api_token`); they MUST be stored hashed.
- In a full load, a Socio whose record is rejected is absent from the staged snapshot and is therefore **deactivated** at activation. A rejected record MUST keep the previous copy of that Socio instead.
- A duplicate `numero_socio` is not validated per record and fails on the database constraint; it MUST be rejected with its own code (`DUPLICATE_NUMERO_SOCIO`).
- The Admin screen of scenario 10 and the audit trail are not built; the prototype exposes the status only to the club.
- There is no 60-minute expiry for incomplete full loads, no watermark check for incremental batches and no limit of records per page or batch.
- The session revocation and login block on a baja need the roster in this backend (the Socio model has no active flag yet).

## Revision Notes

- v3 (HU-N2): synchronization by calling the club API.
- v4: renamed to HU-43 as in the backlog. The club sends the data to endpoints of the system (push); scheduled and on-demand pulls, retries and the club API credential are removed. Contract, rejection handling and idempotency aligned with the prototype.

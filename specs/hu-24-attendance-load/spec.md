# Feature Specification: Load Attendance and Recurring Activities from the Club

**Feature Branch**: `hu-24-attendance-load`
**Created**: 2026-10-11 | **Revised**: 2026-10-25 (v4)
**Status**: Draft
**Backlog Reference**: HU-24 (Estimate: 5, Priority: Alta, MVP: Yes). Needed by HU-25: without it no attendance or participation enters the system.
**Shared rules**: [data contract](../_shared/data-contract.md), [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an Admin, I want to load from the club the attendance at events and the recurring activities, so that the system calculates the impact of that participation on each Socio's scoring."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Load Attendance and Recurring Activities (Priority: P1)

The club **sends** the attendance of each event and the recurring activities (federated sport, subcommissions) to endpoints the system exposes, with the same token, record validation, rejection report and idempotency as the Socio roster (HU-43). The system never calls the club. When the club cannot send the data, the Admin uploads a CSV file with the same data.

**Why this priority**: Attendance and participation are the main inputs to the ranking. Both kinds share one loading mechanism (validation, rejection report, audit), so they live in one story.

**Independent Test**: With the club token, send the attendance of a played event in two pages with one unknown DNI and one mismatched member number, and an activities batch with one future date. Verify the counts and rejections, that the valid records load, that a resend is idempotent, that a second attendance load for the same event waits for the Admin's approval, and that the CSV fallback works.

**Acceptance Scenarios**:

*Attendance sent by the club*

1. **Given** the club has a valid integration token, **When** it sends the attendance of an event (identified by its `id_externo`) as numbered pages (`carga_id`, `pagina`, `total_paginas`), **Then** each page is received and staged, and nothing is applied until the last page arrives.
2. **Given** an attendance load, **When** the event is unknown, or is not a `published` event or a `historical` event with confirmed class or points whose start already passed, **Then** the request is rejected as a whole with the reason and nothing is staged. Both event types are accepted: attendance at a Partido feeds the attendance pillar and attendance at an Evento institucional/amateur feeds the institutional pillar.
3. **Given** the records of a page, **When** they are validated, **Then** each record is identified by DNI and is **rejected individually** when the Socio does not exist, when its `numero_socio` does not belong to that DNI, or when the DNI is repeated in the page. Socios with overdue fees are not a reason for rejection. The valid records are staged and the response lists each rejection with `dni`, `field`, `codigo` and `motivo`.
4. **Given** the last page arrives, **When** a DNI is repeated across pages, **Then** the whole load ends `failed`, nothing is applied and the previous attendance of the event stays as it was.
5. **Given** the last page arrives and the event has **no previous attendance**, **When** the checks pass, **Then** the attendance is applied atomically and the load ends `successful`.
6. **Given** the last page arrives and the event **already has an attendance load**, **When** the checks pass, **Then** the new load is held as `pending approval` and nothing changes yet. The Admin sees the existing load (date, origin, responsible, number of records) next to the new one, and confirms or rejects the replacement. On confirmation the replacement is atomic and the previous load is kept in the history as `replaced`; on rejection the new load ends `rejected` and the existing one stays unchanged.
7. **Given** an attendance load with no valid records, **When** it completes, **Then** nothing is applied and the Admin is informed; it is never read as "nobody attended" and existing data is not modified.

*Recurring activities sent by the club*

8. **Given** the club has a valid token, **When** it sends a batch of activities (`lote_id`, `desde`, `hasta`, records with `dni`, `tipo`, `fecha_desde`, `fecha_hasta`) changed since its last successful send, **Then** each valid record is applied immediately, even if other records of the batch are rejected. The first send covers the last 365 days.
9. **Given** an activity record, **When** it is validated, **Then** it is rejected individually when `tipo` is not `deporte_federado` or `subcomision`, when a date is missing, invalid or in the future, when `fecha_hasta` is before `fecha_desde`, or when the Socio does not exist.
10. **Given** an activity already loaded (same Socio, `tipo` and `fecha_desde`), **When** it is received again, **Then** it is updated, not duplicated, and counted as updated. Activities cannot be deleted in this version.

*Shared rules*

11. **Given** a request whose structure breaks the contract, **When** it is received, **Then** it is rejected as a whole with the error format of the data contract and nothing is applied.
12. **Given** a page or batch already received, **When** the club sends it again with the same content, **Then** the original result is returned and nothing is applied twice. **When** the content differs, **Then** it is rejected with `409 CONFLICT`.
13. **Given** a request without a valid token, **When** it is received, **Then** it is rejected with `401 UNAUTHORIZED` and nothing changes.

*CSV fallback uploaded by the Admin*

14. **Given** the club cannot send the data, **When** the Admin opens the load screen, **Then** they choose what to load ("Asistencia a un evento", selecting an eligible event, or "Actividades recurrentes") and upload a CSV file.
15. **Given** a CSV file, **When** it has a structural problem (not UTF-8 CSV, missing header or required column, empty, larger than 10 MB or with more than 100,000 rows, or for attendance a `fecha_evento` that differs from the date of the selected event), **Then** it is rejected as a whole and nothing is processed.
16. **Given** a structurally valid file, **When** it is processed, **Then** each row is validated with the same rules as the club's records. If more than 5% of the rows are rejected, the whole file is rejected and nothing is applied.
17. **Given** a file for an event that already has attendance, **When** the Admin uploads it, **Then** the system shows the existing load (date, responsible, origin, number of records) and asks for confirmation before replacing it. The replacement is all or nothing and the previous load is kept in the history; if the Admin cancels, the existing load stays unchanged.

*Results*

18. **Given** any load, from the club or from a file, **When** it completes, **Then** the Admin sees how many records were incorporated, updated and rejected, with the rejection reasons, and can download a file with the rejected records.
19. **Given** a load that completed after the latest ranking calculation, **When** the Admin views the ranking status, **Then** the ranking is marked out of date (HU-25).

---

### Edge Cases

- **Attendance, eligible events**: `published` events and confirmed `historical` events whose start already passed. Future, `pending importance definition` and `discarded` events are not eligible.
- **Attendance at elections and assemblies**: loaded like any other event attendance; they are events, not activities.
- **Rejection tolerance**: records sent by the club are rejected one by one and the valid ones load, as in HU-43. The 5% tolerance applies only to CSV files uploaded by the Admin.
- **Volume**: up to 100,000 attendance records per event, sent in pages of up to 10,000 records (data contract, section 5).
- **Interrupted load**: an attendance load whose pages are not all received within 60 minutes of its first page ends `failed` (`LOAD_EXPIRED`): its staged records are discarded, nothing is applied and it accepts no more pages. The club starts a new load with a new `carga_id`.
- **Reliable activities batch**: a batch is accepted only when its `desde` is not later than the `hasta` of the last successful activities batch (the first batch must start at most 365 days back), so no period is left uncovered; otherwise it is rejected whole (`WATERMARK_GAP`).
- **Corrections of attendance**: the club sends a new full attendance load of the event, which goes through the approval of scenario 6.
- **Triggers**: loads happen when the club sends them or when the Admin uploads a file; recalculating the ranking is a separate, manual decision (HU-25).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose authenticated endpoints for the club to send the attendance of an event (paged) and batches of recurring activities, plus a status query of each load.
- **FR-002**: System MUST validate the structure of each request or file first and each record second, rejecting invalid records individually with `codigo` and `motivo`.
- **FR-003**: System MUST apply an attendance load atomically on its last page, or hold it as `pending approval` when the event already has attendance.
- **FR-004**: System MUST let the Admin confirm or reject a pending attendance replacement, keeping the previous load as history.
- **FR-005**: System MUST apply valid activity records immediately, idempotently (upsert by Socio, `tipo`, `fecha_desde`).
- **FR-006**: System MUST be idempotent by `carga_id` + page and by `lote_id`, returning `409` when the content differs.
- **FR-007**: System MUST accept a CSV file from the Admin as fallback, rejecting it whole on structural errors or when more than 5% of its rows are rejected.
- **FR-008**: System MUST report the numbers of records incorporated, updated and rejected, and provide the rejected records with reasons for download.
- **FR-009**: System MUST record the origin of each load (`club` or `file`), make the loaded data available to the scoring engine, and mark the ranking out of date after a load.
- **FR-010**: System MUST authenticate the club with the token shared with HU-43 and HU-21, and audit every load, approval and rejection.

### Key Entities

- **ParticipationLoad**: kind (`attendance` / `activities`), origin (`club` / `file`), `carga_id` / `lote_id`, event (attendance only), state (`receiving` / `processing` / `pending approval` / `successful` / `replaced` / `rejected` / `failed`), pages expected and received, counts (total, incorporated, updated, rejected), payload hash, loaded by (club or Admin), approved or rejected by, timestamps.
- **ParticipationLoadRejection**: load, `dni`, field, code, reason.
- **AttendanceRecord**: Socio, event, load.
- **ActivityRecord**: Socio, type (`deporte_federado` / `subcomision`), from date, to date.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of structurally invalid, failed or empty loads, and over-tolerance files, apply nothing.
- **SC-002**: 100% of attendance replacements need the Admin's explicit approval and are atomic.
- **SC-003**: Every rejected record is reported with a reason.
- **SC-004**: Sending the same page, batch or activity twice creates 0 duplicates.
- **SC-005**: The activities and attendance of the reference dataset contribute exactly the points of the scoring model.

## Assumptions

- The club can send attendance by event `id_externo` (the one it used in HU-21) and activities changed since its last send.
- The CSV file has the same data as the club's records (data contract, sections 3 and 4).
- The rejection codes reuse those of HU-43 where they mean the same (`INVALID_RECORD_FORMAT`, `DUPLICATE_DNI_PAGE`, `DUPLICATE_DNI_ACROSS_PAGES`, `SOCIO_NOT_FOUND`) and add their own (`NUMERO_SOCIO_MISMATCH`, `INVALID_TIPO`, `INVALID_DATE_RANGE`, `FUTURE_DATE`, `EVENT_NOT_ELIGIBLE`).

## Implementation Status

Not implemented yet. It reuses the mechanism of the HU-43 prototype (`gdsi-api-carga-socios`): paged staging with atomic activation for attendance, as its full load; per-record application for activities, as its incremental batch; the same rejection detail, idempotency by payload hash and error body.

## Revision Notes

- v3.3: the system asked the club API for attendance and activities; CSV fallback; 5% tolerance on every load.
- v4: the club sends the data (push), handled like HU-43: records rejected individually, valid ones applied. A second attendance load for an event waits for the Admin's approval. The 5% tolerance now applies only to CSV files.

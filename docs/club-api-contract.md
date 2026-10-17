# Club API contract

**Status:** MVP integration contract for club event and member roster data. It combines the event contract derived from the Pasion de 10 API description and HU-21/HU-22 with the roster contract derived from HU-43. Endpoint paths and wire formats are proposed where the source material is silent.

## Purpose, ownership, and direction

The club is the source of truth for its events and member roster. The club pushes event data, full roster snapshots, and incremental roster changes to the platform. The platform validates and stores a local copy. It does not call or poll a club API, and it does not edit club-owned event or member data. Corrections must come from the club.

The platform owns event importance/category, publication, scoring configuration, and member rankings. Roster data is read-only in the platform and is used for identity checks, fee status, scoring inputs, and ranking eligibility. All operations and identifiers are scoped to the authenticated club.

## Shared transport and authentication

- API base path: `/api/v1`.
- Content type and response format: `application/json; charset=utf-8`.
- Every request uses `Authorization: Bearer <club-api-key>`.
- The platform issues a unique credential to each authorized club. Credentials are confidential, revocable, and must never appear in logs, audit details, or error responses.
- Missing, invalid, expired, or revoked credentials return `401 Unauthorized`; no data is processed.
- A club cannot read or change another club's records. Cross-club identifiers must not reveal whether another club's record exists.
- Timestamps use ISO 8601 with explicit offsets. Persist and compare normalized instants; API responses return UTC timestamps (`Z`). Calendar dates use `YYYY-MM-DD`.

Request-level errors use `{"error":{"code":"...","message":"...","field":"..."}}`; `field` is optional. Codes are stable and machine-readable. Never return credentials, stack traces, sensitive configuration, or another club's data.

## Events

### Ownership and event resource

The club is the source of truth for an event's external ID, title, start time, venue, type, and optional description. The platform assigns an internal ID and manages importance, publication, and scoring configuration. The club cannot set platform state, importance, ranking factors, or publication settings through this API.

| Field | Required | Contract |
|---|---:|---|
| `id_externo` | Yes | Non-empty, stable identifier assigned by the club. Unique per club and used to recognize retries. |
| `id_interno` | Response | Platform-assigned identifier, stable for the event lifetime. |
| `titulo` | Yes | Non-empty event title. |
| `fecha_hora` | Yes | ISO 8601 date-time with explicit UTC offset or `Z`. Compare instants, not local timestamp strings. |
| `lugar` | Yes | Non-empty venue/location. |
| `tipo` | Yes | `Partido` or `Institucional`. |
| `descripcion` | No | Optional context; absent or `null` means no description. |
| `estado` | Response | Platform-owned lifecycle state; see Event lifecycle. |

Example event:

```json
{
  "id_externo": "EVT-1029",
  "titulo": "Partido vs Rivales FC",
  "fecha_hora": "2026-11-20T17:00:00Z",
  "lugar": "Estadio Visitante, calle ejemplo 1234",
  "tipo": "Partido",
  "descripcion": "Fecha 12 del torneo local"
}
```

Missing required fields, empty required strings, invalid types, malformed timestamps, or timestamps without an explicit offset are rejected. The platform retains received source values and records receipt time.

### Event operations

#### Create or refresh one future event

`POST /api/v1/eventos`

Accepts one event. A future event is eligible only when its start time is at least 48 hours after receipt. This applies to both event types, following HU-21's shared publication lead rule.

On success, create the platform event as `pendiente de definición de importancia` and return `201 Created` with `id_interno`, `id_externo`, `estado`, and `fecha_recepcion`. It is not visible to members until publication.

If `id_externo` already exists, a pending event is updated in place subject to validation and the 48-hour guard; preserve its original receipt time, publication deadline, and internal ID. If it is published, historical, or discarded, return `409 Conflict`. No implicit reactivation or replacement occurs.

#### Create a batch of future events

`POST /api/v1/eventos/batch`

Accepts a JSON array of future events only; historical events are not accepted here. Process each item independently using the single-event validation and deduplication rules. Return `207 Multi-Status` with one result per input item, in input order. Each result identifies `id_externo`, outcome, and either `id_interno` or a stable error `code` and `message`. One item's failure does not roll back other valid items. A missing or non-array body returns request-level `400` and processes no items.

#### Read events

`GET /api/v1/eventos`

Returns `200 OK` with a JSON array of events registered for the authenticated club, including platform and external IDs, source fields, lifecycle state, and receipt time. Optional filters are `id_externo`, `id_interno`, and `titulo` (partial, case-insensitive match). Multiple filters combine with AND. No matches returns `[]`. Results are ordered by `fecha_hora`, then `id_interno`.

#### Update a pending event

`PUT /api/v1/eventos/{id_interno}`

Updates a pending event only. The body may change `fecha_hora`, `lugar`, and `descripcion`; include each field being changed, and use `descripcion: null` to clear it. `titulo`, `tipo`, and `id_externo` are immutable through this operation. Return `200 OK` with the updated event. Published, historical, or discarded events return `409 Conflict`.

A proposed update must leave at least 48 hours before start. If the event has already started or is no longer pending, reject without changing it. Accepted changes preserve receipt time and publication deadline and are audited. A changed `tipo` returns `422 Unprocessable Entity`; attempts to change other immutable fields are rejected. A no-op returns `200 OK` and indicates no fields changed.

#### Report a cancellation

`POST /api/v1/eventos/{id_interno}/cancelacion`

The source API does not define cancellation, but HU-21 requires the club to report cancellation of pending events. The proposed request body is `{ "motivo": "..." }`, with `motivo` optional. Return `202 Accepted` and flag the pending event for administrator disposition; do not discard automatically. Repeated notices for the same pending event are idempotent. Non-pending events return `409`; unknown IDs return `404`.

#### Import historical events

HU-21 requires importing already-started events so administrators can classify them and later load attendance. Store them as historical, hidden from members, and exempt from the 48-hour rule. Apply the same event resource validation and prevent duplicate external IDs. The source API defines no historical route. Before implementation, expose a distinct authenticated historical import operation with a documented route and payload; it may be single or batched, but must not reuse the future-event create or batch routes. Batched imports must return per-item validation results.

### Event lifecycle and visibility

| API `estado` | Internal state | Meaning and API effects |
|---|---|---|
| `pendiente de definición de importancia` | `pending importance definition` | Accepted future event, hidden from members. Admin assigns a class for `Partido` or points for `Institucional`. Pending source data can be refreshed without resetting receipt time/deadline. |
| `publicado` | `published` | Visible to members. Platform owns publication and scoring settings. A published `Partido` remains visible until after its start; an institutional event remains visible through the end of its event day. Source-field PUT updates are not accepted. |
| `histórico` | `historical` | Past event imported as history; hidden from members and available for attendance recording. |
| `descartado` | `discarded` | Admin discarded a pending/cancelled event; hidden and cannot score. Create retry cannot restore it. |

Cancellation flags a pending event for administrator review and withholds it from automatic publication until disposition. Omission from a partial submission is not evidence of cancellation. Publication timing and defaults follow HU-22 and the source API: automatic publication at the earlier of 24 hours after import or 48 hours before start; default `B` for matches and 20 points for institutional events. Creation does not mean publication.

### Event errors and audit

| HTTP status | Event use |
|---|---|
| `201 Created` | Single event created or accepted as pending. |
| `202 Accepted` | Cancellation notice accepted for administrator disposition. |
| `200 OK` | Query or update succeeded, including a no-op. |
| `207 Multi-Status` | Batch processed; inspect each item result. |
| `400 Bad Request` | Malformed JSON, missing required field, invalid field format/request shape. |
| `404 Not Found` | `id_interno` does not identify an event for this club. |
| `409 Conflict` | External ID conflicts with a lifecycle state that disallows retry/update, or immutable identity conflict. |
| `422 Unprocessable Entity` | Business rule violation, including less than 48 hours, attempted type change, or update after event end. |

Each accepted creation/import/update, rejected validation attempt, and administrator discard is auditable with actor/source, timestamp, external and internal IDs where available, outcome, and changed values. Authentication secrets are excluded. A `400`, `401`, `404`, `409`, or `422` must not partially mutate the target event.

## Member roster (Socios)

### Ownership and Socio resource

The club is the source of truth for its member roster (padrón). The platform keeps a read-only local copy for identity checks, fee status, scoring, and ranking eligibility. The integration supports up to 500,000 Socios using paged/chunked full snapshots and incremental changes. A failed or critically interrupted load must retain the last valid local copy.

| Field | Required | Contract |
|---|---:|---|
| `id_externo` | Yes | Stable club-assigned member identifier; identity key for updates/removals, unique within club. |
| `dni` | Yes | Member identity number in the agreed club format; unique within roster. Duplicate DNI records are rejected. |
| `numero_socio` | Yes | Club member number, unique within club. |
| `nombre` | Yes | Member's full name. |
| `fecha_nacimiento` | Yes | Valid calendar date (`YYYY-MM-DD`). |
| `fecha_alta` | Yes | Valid membership start date (`YYYY-MM-DD`). |
| `fecha_baja_previa` | No | Previous membership end date, if provided; `null` when absent. Retained for scoring/history rules. |
| `estado_cuota` | Yes | Current fee status; agreed values must distinguish at least `al_dia` and `moroso`. |
| `email` | Yes | Registered email address with valid email format. |
| `distancia_km` | Yes | Non-negative distance to the club stadium used by scoring. Club supplies it or an agreed precomputed value. |
| `localidad` | Conditional | Optional locality for display/analysis; does not replace `distancia_km` in scoring. |
| `fecha_modificacion` | Incremental | Timestamp for this version/change, ISO 8601 with explicit offset. |

No exact home address is accepted or stored. The source mentions “distancia/localidad”; this contract requires `distancia_km` for scoring and treats `localidad` as optional pending club confirmation. `fecha_baja_previa` is included from the shared data contract. Fee-state values, identifier formats, and whether email can be absent must be agreed before production; missing/invalid email is rejected under HU-43.

Example Socio:

```json
{
  "id_externo": "SOC-1029",
  "dni": "30123456",
  "numero_socio": "A-4521",
  "nombre": "Nombre Apellido",
  "fecha_nacimiento": "1985-04-12",
  "fecha_alta": "2010-03-01",
  "fecha_baja_previa": null,
  "estado_cuota": "al_dia",
  "email": "socio@example.org",
  "distancia_km": 12.4,
  "localidad": "Ciudad",
  "fecha_modificacion": "2026-10-16T12:30:00Z"
}
```

### Roster operations

#### Administrator-requested resynchronization

An Administrator may mark a roster as needing a fresh push. This is an internal platform workflow, not an outbound API call. The club is notified through an agreed operational channel and submits a full or incremental load. The notification channel is outside this contract.

#### Submit a full roster snapshot

`POST /api/v1/socios/cargas/completa`

Submits a complete snapshot in pages/chunks. Each chunk includes a common `carga_id`, one-based `pagina`, `total_paginas`, and array `socios`:

```json
{
  "carga_id": "full-2026-10-16-001",
  "pagina": 1,
  "total_paginas": 250,
  "socios": [
    {
      "id_externo": "SOC-1029",
      "dni": "30123456",
      "numero_socio": "A-4521",
      "nombre": "Nombre Apellido",
      "fecha_nacimiento": "1985-04-12",
      "fecha_alta": "2010-03-01",
      "fecha_baja_previa": null,
      "estado_cuota": "al_dia",
      "email": "socio@example.org",
      "distancia_km": 12.4,
      "fecha_modificacion": "2026-10-16T12:30:00Z"
    }
  ]
}
```

Return `202 Accepted` for a valid chunk and identify its `carga_id`, page, and receipt status. Do not activate the snapshot until all expected pages arrive and structural checks pass. Retries of the same `carga_id` and page are idempotent under the agreed retry policy; the club must not reuse a `carga_id` for different contents.

Validate records individually. Stage valid records and report invalid ones with external ID (when present), field, stable rejection code, and reason. Detect duplicate DNI across pages at finalization. If page structure is invalid, pages are missing, the load is critically interrupted, or final consistency checks fail, reject the snapshot and retain the last successful roster. Final activation after all pages is transactional.

#### Submit incremental changes

`POST /api/v1/socios/cargas/incremental`

Submits changes since the last successful delivery. The body contains unique `lote_id`, `desde` and `hasta` watermarks (ISO 8601 timestamps), and `cambios`. Each change has `accion` (`alta`, `modificacion`, or `baja`) and `socio` for adds/updates, or `id_externo` for removals:

```json
{
  "lote_id": "delta-2026-10-16-001",
  "desde": "2026-10-15T12:00:00Z",
  "hasta": "2026-10-16T12:00:00Z",
  "cambios": [
    { "accion": "modificacion", "socio": { "id_externo": "SOC-1029", "dni": "30123456", "numero_socio": "A-4521", "nombre": "Nombre Apellido", "fecha_nacimiento": "1985-04-12", "fecha_alta": "2010-03-01", "fecha_baja_previa": null, "estado_cuota": "moroso", "email": "socio@example.org", "distancia_km": 12.4, "fecha_modificacion": "2026-10-16T11:30:00Z" } },
    { "accion": "baja", "id_externo": "SOC-77" }
  ]
}
```

`desde` is exclusive and `hasta` inclusive. Apply changes after structural validation, with individual record validation results. A repeated `lote_id` with identical content returns its original result and does not apply changes twice. The club advances its watermark only after successful acknowledgement. If incremental history is unavailable, use a new full snapshot.

A member marked `baja` becomes inactive and ineligible for future rankings, while attendance, scores, and audit history are retained. Fee status changes take effect in the local copy; becoming up to date restores eligibility at the next ranking calculation without losing accumulated history.

#### Check load status and retrieve results

`GET /api/v1/socios/cargas/{carga_id}`

Returns `200 OK` with load type, status (`recibiendo`, `procesando`, `exitosa`, or `fallida`), start/completion timestamps, counts created/updated/deactivated/rejected, full snapshot page progress, and rejected-record details or a downloadable report reference. Administrators can see the latest received load's timestamp and outcome. This endpoint is the proposed way for the club to retrieve final rejection details; webhook behavior is not specified.

### Roster validation, responses, and application

- The body must match the declared schema. Invalid envelope structure or incompatible field types fail the request/load; the last active roster remains intact.
- Duplicate DNI, missing/invalid birth date, missing/invalid membership start date, or malformed email are record-level rejects. Other field validation follows the data contract agreed with the club.
- `id_externo`, `dni`, and `numero_socio` must map consistently. Identifying field changes require confirmation that the external ID still identifies the same person; otherwise reject for administrator review.
- Valid records in an incremental batch may apply even when other records are rejected; report each rejection. A structurally invalid or critically interrupted batch applies no changes.
- Full snapshot activation and incremental commits are transaction-safe. Source-owned roster fields cannot be manually overwritten by administrators.

| HTTP status | Roster use |
|---|---|
| `202 Accepted` | A valid page or batch was received and is being processed. |
| `200 OK` | Load status/result query succeeded. |
| `400 Bad Request` | Malformed JSON, missing envelope fields, invalid page/batch structure; request data is not applied. |
| `404 Not Found` | Unknown load ID. |
| `409 Conflict` | Conflicting retry, reused load ID with different content, invalid page sequence, or conflicting active load. |
| `422 Unprocessable Entity` | Valid envelope violates business rules; record-level errors are normally in the load report. |

Load results include per-record rejections with `id_externo` when available, `field`, stable `code`, and concise `message`. Each accepted delivery and completion/failure is recorded with club, load ID, type, receipt and processing timestamps, result, and created/updated/deactivated/rejected counts.

### Roster freshness and performance

- If no successful roster load completes within the last 24 hours by default (configurable), warn before ranking calculation and wave segmentation.
- Initial load target: up to 500,000 Socios in less than one hour. Data discrepancy target: below 0.1%. These targets require validation with the club service.
- Preserve the last known good roster until new data commits safely. Audit and report failed deliveries. Retry transient failures with progressive backoff where the integration process initiates retries.
- Email and fee-status changes take effect after successful application. Ranking eligibility changes on the next ranking calculation; roster ingestion does not silently recalculate rankings.

## Decisions to resolve before implementation

1. Define the distinct historical event import route and payload; it is required by HU-21 but absent from the source API.
2. Confirm the proposed cancellation route and optional `motivo` with the club; the source API defines no cancellation operation.
3. The source API applies a 48-hour minimum to new matches and edited match start times. HU-21 applies publication lead to all upcoming events and pending updates; this contract follows HU-21 for both event types.
4. The source API says duplicate event IDs conflict, while HU-21 requires pending records to update on resend. This contract updates pending events and keeps `409` for other states.
5. Confirm canonical Socio fields, identifier formats, nullability, fee-state enum, and whether email may be absent.
6. Agree maximum request/page size, supported precision, rate limits, retry policy, and whether roster push is synchronous or asynchronous.
7. The event source does not define detailed response schemas, batch item shape, PUT body semantics, or timestamp handling. These are made explicit above; PUT only edits `fecha_hora`, `lugar`, and `descripcion`, and only while pending.
8. Agree resynchronization notification channel and operational thresholds with the club.

## Source references

- `api pasion de 10.pdf`, sections 1.1–1.4: event fields, checks, lifecycle, routes, responses, bearer API-key authentication.
- `Artefactos TP G6.xlsx - Backlog - US.csv`, HU-21: event ingestion, pending updates, lead-time checks, historical imports, cancellations, and audit requirements.
- Same backlog, HU-22: importance assignment, visibility, publication timing, and defaults.
- Same backlog, HU-43: authenticated full/incremental roster loads, validation, read-only copy, removals, freshness warnings, security, and performance objectives.
- `specs/_shared/data-contract.md`, section 1: canonical scoring/identity fields, fee-status handling, distance, and 500,000-member volume.
- `specs/hu-43-club-data-sync/spec.md`: club-initiated pushes, pagination, retries, and last-good-copy behavior.

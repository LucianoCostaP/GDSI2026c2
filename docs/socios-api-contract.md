# Socios API contract

**Status:** MVP integration contract derived from HU-43 in the product backlog. Endpoint paths and wire formats below make the backlog implementable; they are proposed contract details where HU-43 is silent.

## Purpose and ownership

The club is the source of truth for its member roster (padrón). The club pushes a full initial roster and later incremental changes to endpoints provided by the platform. The platform keeps a read-only local copy and uses it for identity checks, fee status, scoring inputs, and ranking eligibility. The platform does not create or edit club member data. All corrections must come from the club.

The roster is club-scoped. The integration must support a population of up to 500,000 Socios using paged/chunked transmission. Full loads establish or replace a roster snapshot; incremental loads report additions, updates, and removals since the last successful delivery. The system must retain the last valid local copy if a full load or incremental delivery fails structurally or is interrupted critically.

## Transport and authentication

- Base path: `/api/v1/socios`.
- Content type and response format: `application/json; charset=utf-8`.
- Every request uses `Authorization: Bearer <club-api-key>`.
- The platform issues credentials to the authorized club for pushing data. Credentials are secret, may be revoked, and must never appear in logs, audit details, or error responses.
- Missing, invalid, expired, or revoked credentials result in `401 Unauthorized`; the request has no effect.
- Each request and each record is scoped to the authenticated club. A club cannot load, update, or remove another club's Socios.

## Socio resource

| Field | Required | Contract |
|---|---:|---|
| `id_externo` | Yes | Stable club-assigned member identifier. The identity key for updates and removals. Must be unique within the club. |
| `dni` | Yes | Member national identity number. Must be valid in the agreed club format and unique within the roster. Duplicate DNI records are rejected. |
| `numero_socio` | Yes | Club member number; unique within the club. |
| `nombre` | Yes | Member's full name. |
| `fecha_nacimiento` | Yes | Valid ISO 8601 calendar date (`YYYY-MM-DD`). |
| `fecha_alta` | Yes | Valid ISO 8601 calendar date (`YYYY-MM-DD`) representing club membership start. |
| `fecha_baja_previa` | No | Previous membership end date, if the club provides it; `null` when absent. Retained for scoring/history rules. |
| `estado_cuota` | Yes | Current fee status. Allowed values must be agreed with the club; the platform needs to distinguish at least `al_dia` and `moroso`. |
| `email` | Yes | Registered email address. Must pass email-format validation. |
| `distancia_km` | Yes | Distance to the club stadium used by scoring, as a non-negative number. The club supplies this value or a value agreed to be precomputed. |
| `localidad` | Conditional | Locality may be provided for display/analysis if required. It does not replace `distancia_km` in scoring. |
| `fecha_modificacion` | Yes for incremental changes | Club timestamp identifying when this version/change was recorded; ISO 8601 with explicit offset. |

No exact home address is accepted or stored. The backlog mentions “distancia/localidad” while the shared data contract uses distance in kilometers and requires no address; this contract treats `distancia_km` as required for scoring and `localidad` as optional pending confirmation with the club. `fecha_baja_previa` comes from the shared data contract and is included as optional because HU-43 does not list it explicitly.

Example member record:

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

The exact enums for `estado_cuota`, the club's identifier formats, and whether email may be absent are not defined in HU-43. The platform requires an unambiguous current fee state and valid email format; these code lists and nullability rules must be agreed before production integration. A missing or invalid email is rejected under HU-43.

## Operations

### Administrator-requested resynchronization

An Administrator may mark a roster as needing a fresh push. This is an internal platform workflow, not an outbound call or an API operation against the club. The club is notified through an agreed operational channel and submits a full or incremental load using the endpoints above. The notification channel is outside this API contract and must be agreed with the club.

### Submit a full roster snapshot

`POST /api/v1/socios/cargas/completa`

Submits a complete snapshot in pages/chunks. Each chunk includes a common `carga_id`, a one-based `pagina`, `total_paginas`, and an array `socios`:

```json
{
  "carga_id": "full-2026-10-16-001",
  "pagina": 1,
  "total_paginas": 250,
  "socios": [ { "id_externo": "SOC-1029", "dni": "30123456", "numero_socio": "A-4521", "nombre": "Nombre Apellido", "fecha_nacimiento": "1985-04-12", "fecha_alta": "2010-03-01", "fecha_baja_previa": null, "estado_cuota": "al_dia", "email": "socio@example.org", "distancia_km": 12.4, "fecha_modificacion": "2026-10-16T12:30:00Z" } ]
}
```

The API returns `202 Accepted` for a valid chunk and identifies its `carga_id`, page, and receipt status. A full snapshot is not made active until every expected page is received and the snapshot passes structural checks. Retries of the same `carga_id` and page replace that page idempotently; conflicting content for an already accepted page is rejected unless the page is explicitly resent under the agreed retry policy. The club must not reuse a `carga_id` for different snapshot contents.

Records are validated individually. Valid records are staged for the snapshot; invalid records are reported with their external ID (when present), field, stable rejection code, and reason. Duplicate DNI across pages is detected at snapshot finalization. If the request/page structure is invalid, pages are missing, the load is interrupted critically, or final consistency checks fail, the snapshot is rejected and the last successful roster remains active. HU-43 requires record-level rejects and all-or-nothing protection for structural/critical failures; final activation after complete page receipt is an explicit transaction rule to avoid exposing a partial roster.

### Submit incremental changes

`POST /api/v1/socios/cargas/incremental`

Submits records changed since the last successful delivery. Body contains a unique `lote_id`, the club's `desde` and `hasta` watermarks (ISO 8601 timestamps), and `cambios`, an array of change objects. Each change has `accion` (`alta`, `modificacion`, or `baja`) and `socio` for adds/updates, or `id_externo` for removals:

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

`desde` is exclusive and `hasta` inclusive. Changes in a successful batch are applied atomically after structural validation, with individual record validation results. A repeated `lote_id` with identical content returns the original result and does not apply changes twice. The club advances its watermark only after a successful acknowledgement. If incremental history is unavailable, the club and platform must use a new full snapshot.

A member marked `baja` becomes inactive and ineligible for future rankings, but the platform retains their attendance, score, and audit history. A fee-status change is reflected in the local copy; becoming up to date restores eligibility at the next ranking calculation without losing accumulated history.

### Check load status and retrieve results

`GET /api/v1/socios/cargas/{carga_id}`

Returns `200 OK` with the load type, status (`recibiendo`, `procesando`, `exitosa`, or `fallida`), start/completion timestamps, counts created/updated/deactivated/rejected, page progress for a full snapshot, and rejected-record details or a downloadable report reference. The platform also exposes the latest received load's timestamp and outcome to administrators, as required by HU-43.

The backlog requires the club and administrator to receive rejection details. This endpoint is the proposed way for the club to retrieve the final report; asynchronous notification/webhook behavior is not specified and is not assumed.

## Validation and application rules

- The request body must match the declared schema. Unknown required structure changes or incompatible field types fail the load; the previous active roster remains intact.
- Records with duplicate DNI, missing/invalid birth date, missing/invalid membership start date, or malformed email are rejected individually with a reason. Any additional required field validation follows the data contract agreed with the club.
- `id_externo`, `dni`, and `numero_socio` must map consistently. Changes to identifying fields are allowed only if the club confirms the existing `id_externo` identifies the same person; otherwise the record is rejected for administrator review. The backlog does not specify identity reassignment semantics.
- Valid records in an incremental batch can be incorporated even when other records are rejected, and the report lists each rejected record. A structurally invalid or critically interrupted batch applies no changes.
- Full snapshot activation and incremental commits must be transaction-safe. A failed operation never leaves a partially applied/corrupted local copy.
- Source-owned roster fields are read-only in the platform UI and cannot be manually overwritten by administrators.

## Responses and errors

Suggested status codes:

| HTTP status | Use |
|---|---|
| `202 Accepted` | A valid page or batch was received and is being validated/processed. |
| `200 OK` | Load status/result query succeeded. |
| `400 Bad Request` | Malformed JSON, missing required envelope fields, invalid page/batch structure. No data from that request is applied. |
| `401 Unauthorized` | Missing or invalid bearer token. No data is processed. |
| `404 Not Found` | Unknown load ID. |
| `409 Conflict` | Conflicting retry, reused load ID with different content, invalid page sequence, or conflicting active load. |
| `422 Unprocessable Entity` | Envelope is valid but the load violates business rules. Record-level data errors are normally returned in the load report. |

Request-level errors use `{"error":{"code":"...","message":"..."}}`. Load results include per-record rejections with `id_externo` when available, `field`, stable `code`, and a concise `message`. Never return credentials, stack traces, or another club's data. Error codes are stable for client handling.

## Synchronization, freshness, and audit

- Each accepted delivery and completion/failure is recorded with club, load ID, type, receipt and processing timestamps, result, and counts of created, updated, deactivated, and rejected Socios.
- The administrator can see the latest load timestamp and outcome. If no successful roster load has completed within the last 24 hours by default (configurable), warn before ranking calculation and wave segmentation.
- Initial load target: up to 500,000 Socios in less than one hour. Data discrepancy target: below 0.1%. These are performance/consistency objectives subject to validation with the club service.
- Full and incremental imports preserve the last known good roster until the new data is safely committed. Failed deliveries are audited and reported to administrators; the platform retries transient failures using progressive backoff where the integration process initiates retries.
- Email and fee-status changes become effective in the local copy after successful application. Rank eligibility changes on the next ranking calculation; the platform does not silently recalculate the ranking as part of roster ingestion.

## Differences and decisions to resolve

1. The architecture is push-only: the club sends roster data to the platform's authenticated API. HU-N2 and the shared data contract specify that direction.
2. HU-43 names fields including member identifier, DNI, name, birth date, alta date, fee status, email, and “distancia/localidad”. The shared data contract also requires distance in km and includes previous baja date. Confirm the canonical field list, identifiers, nullability, and fee-state enum with the club.
3. HU-43 requires full rosters “in lots/paged” and incremental changes, but does not define pagination envelopes, completion/finalization behavior, delta watermarks, or retries. This contract proposes chunked snapshots with `carga_id` and atomic activation, plus incremental batches with watermarks and idempotent `lote_id`.
4. Agree maximum request/page size, supported date/time precision, rate limits, and whether a push is synchronous or asynchronous. These operational values are not stated in the backlog.
5. The backlog says record-level errors are rejected individually, but also says critical interruption/schema failure rejects the operation without partial corruption. This contract distinguishes record rejects (other valid rows may apply) from envelope/critical failures (no commit).

## Source references

- `Artefactos TP G6.xlsx - Backlog - US.csv`, HU-43: authenticated full and incremental roster loads, validation, read-only copy, removals, freshness warnings, security, and performance objectives.
- `specs/_shared/data-contract.md`, section 1: canonical scoring/identity fields, fee-status handling, distance, and 500,000-member volume.
- `specs/hu-n2-club-data-sync/spec.md`: related draft sync story, aligned to club-initiated pushes, pagination, retries, and last-good-copy behavior.

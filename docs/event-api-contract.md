# Event API contract

**Status:** MVP integration contract derived from the Pasion de 10 API description and the event stories in the product backlog (HU-21 to HU-23).

## Purpose and ownership

The club's system is the source of truth for an event's external ID, title, start date and time, venue, type, and optional description. The club pushes event data to endpoints provided by the platform. The platform accepts and validates that data, assigns its own internal ID, and manages importance, publication, and scoring configuration. The club cannot set platform state, importance, ranking factors, or publication settings through this API. The platform does not call or pull from a club API.

This contract covers event submission, retrieval, and updates. The PDF describes individual and batch submission, query, and update endpoints. HU-21 additionally requires historical event ingestion; the PDF does not define a historical-ingestion route or payload. That capability is therefore specified below as a required operation whose transport route must be agreed before implementation. It must not be silently treated as the future-event batch route. GET is available to the club as a read operation; event data flows into the platform through club-initiated POST/PUT requests, never through platform polling.

## Transport and authentication

- Base path: `/api/v1`.
- Content type and response format: `application/json` (UTF-8 encoded).
- Every request uses `Authorization: Bearer <club-api-key>`.
- The platform issues a unique alphanumeric key to the authorized club. Keys are confidential, revocable, and must not appear in logs or error messages.
- Missing, invalid, expired, or revoked credentials result in `401 Unauthorized`; the request has no effect.
- Authenticated requests that fail validation or authorization also have no effect on existing data, except that a batch may report independent per-item outcomes as described below.

## Event resource

| Field | Required | Contract |
|---|---:|---|
| `id_externo` | Yes | Non-empty, stable identifier assigned by the club. Unique per club; the idempotency key for retries. |
| `id_interno` | Response | Platform-assigned identifier. Stable for the lifetime of the platform event. |
| `titulo` | Yes | Non-empty event title. |
| `fecha_hora` | Yes | ISO 8601 date-time with an explicit UTC offset or `Z`. The platform compares instants, not local timestamp strings. |
| `lugar` | Yes | Non-empty venue/location. |
| `tipo` | Yes | `Partido` or `Institucional`. The platform may display institutional events as institutional/amateur events. |
| `descripcion` | No | Optional contextual description; absent or `null` means no description. |
| `estado` | Response | Platform-owned lifecycle state; see Lifecycle below. |

Example request:

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

The PDF example lists these fields. HU-21 calls for date, time, venue, type, and club external ID; the title and optional description are also retained because the API description defines them. Missing required fields, empty required strings, invalid types, malformed timestamps, or timestamps without an explicit offset are rejected. The platform retains the received source values and records receipt time.

## Operations

### Create one future event

`POST /api/v1/eventos`

Accepts one event resource. Future events are eligible only when their start time is at least 48 hours after receipt. This rule applies to both types because HU-21 says events starting in less than 48 hours cannot be published; the PDF expressly calls out matches. The platform must use the stricter shared backlog rule.

On success, create the platform event as `pendiente de definición de importancia` and return `201 Created`. The PDF explicitly requires the response to return `id_interno`; this contract proposes also returning `id_externo`, `estado`, and `fecha_recepcion`. It is not visible to members until publication.

If `id_externo` already exists:

- If it is pending, treat the call as an update to source fields, subject to all validation and the 48-hour guard. Preserve the original receipt time and publication deadline. Do not create a second event.
- If it has been published, do not overwrite it through create. Return `409 Conflict` and direct the club to `PUT /api/v1/eventos/{id_interno}`.
- If it is historical, discarded, or retired, return `409 Conflict`; no implicit reactivation or replacement occurs.

The PDF says duplicate IDs return conflict, while HU-21 expressly requires pending-event resends to update. The backlog behavior governs retries for pending events; conflict remains the behavior for other existing lifecycle states.

### Create a batch of future events

`POST /api/v1/eventos/batch`

Accepts a JSON array of event resources. This endpoint is for future events only and does not accept historical events. Each item is processed independently and must follow the same validation, deduplication, and minimum lead-time rules as single creation. Return `207 Multi-Status` with one result per input item, in input order. Each result identifies `id_externo`, outcome, and either the created/updated `id_interno` or a stable error `code` and human-readable `message`. A failure for one item does not roll back other valid items.

The PDF specifies `207` but not the response schema; the per-item shape above is the contract needed to make partial success actionable. A missing or non-array body is a request-level `400` and processes no items.

### Read events

`GET /api/v1/eventos`

Returns `200 OK` and a JSON array of events registered for the authenticated club, including their platform IDs, external IDs, source fields, lifecycle state, and receipt time. The PDF does not limit this query to published/visible events. Optional filters:

- `id_externo={id}`
- `id_interno={id}`
- `titulo={text}` (partial, case-insensitive match)

Multiple filters are combined with AND. No matches returns `200 OK` with `[]`. Results have a stable ordering by `fecha_hora`, then `id_interno`. The PDF defines the filters and `200` response but not matching semantics or response fields; these defaults make the operation deterministic.

### Update an event

`PUT /api/v1/eventos/{id_interno}`

Updates the fields the PDF lists: date/time (`fecha_hora`), venue (`lugar`), and description (`descripcion`). The PDF does not specify whether this PUT uses a partial or full replacement body; this contract requires the fields being changed and allows `descripcion: null` to clear it. `titulo`, `tipo`, and `id_externo` are immutable through this operation because the PDF does not list them as editable. The platform returns `200 OK` with the updated event; returning the full updated resource is a contract detail beyond the PDF's stated response.

Updates are rejected if the event has already ended. For a pending event, a proposed update that leaves less than 48 hours before start is rejected, consistent with HU-21. For a published event, the backlog's HU-23 rule permits reprogramming without the initial 48-hour publication restriction; this differs from the PDF, which says a changed `fecha_hora` for a `Partido` must remain at least 48 hours ahead of the edit. This contract follows the backlog for published events, so it is a deliberate product-rule deviation from the PDF. Changes to an active published event's date, time, or venue become visible promptly; the platform gives the administrator 24 hours to review importance values. The platform applies the HU-23 wave-schedule consequences and records old and new values in its audit log.

If the proposed `tipo` differs from the stored type, return `422 Unprocessable Entity` and make no changes. Attempts to change fields not editable through PUT are rejected; the exact status for those immutable-field errors is an implementation detail to standardize. If club data cannot be validated, leave the event unchanged. A no-op update returns `200 OK` and reports that no fields changed.

### Report an event cancellation

`POST /api/v1/eventos/{id_interno}/cancelacion`

The PDF does not define a cancellation operation. HU-21/HU-23 require the club to report cancellations, so this contract proposes an authenticated endpoint using the platform event ID returned by the create response or event query. The request body is `{ "motivo": "..." }`, with `motivo` optional because the backlog does not require the club to provide one. Return `202 Accepted` and mark the event for administrator disposition; do not change it automatically to `descartado` or `retirado`. An administrator discards a pending event or withdraws a published event through the platform workflow. Repeated cancellation notices are idempotent. Unknown IDs return `404 Not Found`.

### Import historical events

The platform must support import of already-started events, as required by HU-21, so administrators can classify them and later load attendance. They are stored as historical, are not published or shown to members, and are exempt from the 48-hour lead-time rule. Their type, title, date/time, venue, external ID, and optional description follow the same event resource rules. An existing external ID must not create a duplicate.

The source PDF explicitly says the future batch endpoint does not accept history, and does not provide a separate historical endpoint. Before implementation, expose a distinct authenticated historical import operation and document its route and payload. The operation may be single or batch, but must distinguish historical imports from future event creation and return per-item validation results if batched. Historical records must not be accepted via `POST /api/v1/eventos` or `/batch`.

## Lifecycle and visibility

The API `estado` values below are Spanish wire values. The story specs and persistence model use the corresponding English state codes:

| API `estado` value | Spec/internal state | Meaning and API effects |
|---|---|---|
| `pendiente de definición de importancia` | `pending importance definition` | Accepted future event; not visible to members. Admin must assign class for `Partido` or points for `Institucional`. Pending source data may be refreshed without changing receipt time/deadline. |
| `publicado` | `published` | Visible to members. Platform owns transition and scoring configuration. Club may update eligible source fields through PUT; no re-publication or duplicate is created. Per the PDF, a published `Partido` remains visible until after its start, while an institutional event remains visible through the end of its event day. |
| `histórico` | `historical` | Past event imported as history; not visible to members and available for attendance recording. |
| `descartado` | `discarded` | Admin discarded a pending/cancelled event; not visible and cannot score. No API create retry may restore it. |
| `retirado` | `withdrawn` | Admin withdrew a published event; not visible and cannot accept attendance or score. Restoration is platform-admin controlled. |

For HU-21/HU-23, the proposed cancellation operation flags an event for administrator review. A pending event is withheld from automatic publication until disposition; the administrator may discard it. A published event remains published until the administrator withdraws it. The platform cannot infer cancellation from omission in a partial POST or batch.

Publication, scoring class/points, default values, deadlines, attendance, and member visibility remain platform responsibilities. Platform publication timing and defaults follow HU-22 and the PDF: automatic publication at the earlier of 24 hours after import or 48 hours before start; default `B` for matches and 20 points for institutional events. The API response to creation does not mean the event is published.

## Validation and error responses

| HTTP status | Use |
|---|---|
| `201 Created` | Single event created or accepted as a pending event. |
| `202 Accepted` | Cancellation notice accepted and flagged for administrator disposition (proposed operation, not in PDF). |
| `200 OK` | Query or update succeeded, including a no-op update. |
| `207 Multi-Status` | Batch processed; inspect each item result. |
| `400 Bad Request` | Malformed JSON, missing required field, invalid field format, or invalid request shape. No event is created for a single request. |
| `401 Unauthorized` | Missing or invalid bearer token. No data is processed. |
| `404 Not Found` | `id_interno` does not identify an event for this club. |
| `409 Conflict` | External ID conflicts with an event whose state does not permit create retry/update, or immutable identity conflict. |
| `422 Unprocessable Entity` | Valid JSON but business rule violation, including less than 48 hours for a future event, attempted type change, or update after event end. No proposed changes are applied. |

Errors use a consistent JSON object: `{"error":{"code":"...","message":"...","field":"..."}}`; `field` is optional. Never include credentials, internal stack traces, or sensitive configuration. Error codes are stable machine-readable identifiers. Batch item errors use the same `code` and `message` fields. A `400`, `401`, `404`, `409`, or `422` response must not partially mutate the target event.

## Idempotency, audit, and time

- `id_externo` is unique within the club and is used to recognize retries. Repeated pending-event submissions update permitted source values in place; they do not reset receipt time, publication deadline, or internal ID.
- Each accepted creation/import/update, rejected validation attempt, and administrator discard is auditable with actor/source, timestamp, external and internal IDs where available, outcome, and changed values. Authentication secrets are excluded.
- All timestamps are ISO 8601 with an explicit offset. Persist and compare normalized instants; return UTC timestamps (`Z`) in API responses. The lead-time check uses the platform server clock at receipt/commit time.
- Requests are authorized for the sending club's data only. Cross-club IDs must not reveal whether another club's record exists.

## Differences to resolve before implementation

1. Define the historical import route and payload; it is required by HU-21 but absent from the PDF endpoints.
2. The PDF has no cancellation route. This contract proposes `POST /api/v1/eventos/{id_interno}/cancelacion`; confirm the route and optional `motivo` field with the club before implementation. Omission from a partial submission is not sufficient evidence of cancellation.
3. The PDF explicitly applies the 48-hour minimum to new `Partido` submissions and edited `Partido` start times. HU-21 applies the publication lead to all upcoming events and pending updates. This contract follows HU-21 for creation and pending updates, applying it to both types.
4. The PDF says a `Partido`'s new date/time on PUT must remain at least 48 hours after the edit. HU-23 allows reprogramming an already published event without that initial-publication lead. This contract follows HU-23 for published events, so implementation intentionally differs from the PDF rule in that case. Pending events still must meet 48 hours.
5. The PDF says duplicate external IDs return `409`; HU-21 requires pending records to update on resend. This contract treats pending resends as updates and keeps `409` for other states.
6. The PDF does not define detailed response schemas, batch item shape, PUT body semantics, or timestamp timezone handling. These are made explicit here for implementation consistency. It lists only `fecha_hora`, `lugar`, and `descripcion` as PUT-editable fields; `titulo` is not editable through PUT under this contract.

## Source references

- `api pasion de 10.pdf`, sections 1.1-1.4: event fields, automated checks, lifecycle, routes, example responses, and bearer API-key authentication.
- `Artefactos TP G6.xlsx - Backlog - US.csv`, HU-21: authenticated event ingestion, pending updates, lead-time checks, malformed-input rejection, historical imports, cancellation handling, and audit requirements.
- Same backlog, HU-22: importance assignment, visibility, automatic publication timing and defaults.
- Same backlog, HU-23: published event reprogramming and its effect on review and wave schedules.

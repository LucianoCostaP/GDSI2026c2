# Data Contract (inputs from the club)

The system never edits Socio personal data (it is outside the product scope). The club **sends** the data below to an integration API that the system exposes (section 5): the Socio roster (HU-43), events (HU-21, HU-23), attendance and recurring activities (HU-24). The system never calls an API of the club. The only data the Admin enters is the class or the points of an event, and the CSV file used as fallback for HU-24.

Field names are the wire names of the integration API, as implemented in the prototypes `gdsi-api-carga-socios` (roster) and `API-Eventos-Pasion-de-10` (events).

## 1. Socio reference data (read-only, sent by the club, HU-43)

| Field | Required | Used by |
|---|---|---|
| `id_externo` (unique per club) | Yes | key of the Socio in the club; upserts and bajas |
| `dni` (unique) | Yes | identification, tiebreak (lower document number), attendance and participation records |
| `numero_socio` (unique) | Yes | identification |
| `nombre` | Yes | display |
| `email` (valid format) | Yes | OTP and activation codes |
| `fecha_nacimiento` (`YYYY-MM-DD`) | Yes | age E (P_antigüedad, tiebreak) |
| `fecha_alta` (`YYYY-MM-DD`) | Yes | seniority T, new-member bonus t |
| `fecha_baja_previa` (`YYYY-MM-DD`) | No | new-member bonus (re-entry filter) |
| `estado_cuota` (`al_dia` / `moroso`) | Yes | HU-01, ranking eligibility, wave segmentation |
| `distancia_km` (≥ 0) | Yes | distance from the Socio's home to the club stadium, P_distancia |
| `localidad` | No | display only; never a home address |
| `fecha_modificacion` (ISO 8601 with offset) | No | when the club last changed the record |

Rules:

- **Venue model**: every event of type "Partido" takes place at the club stadium, so one distance per Socio is enough. Events held at other venues are registered as "Evento institucional/amateur" and score as institutional events.
- **Source of truth**: the club. The system keeps the copy it receives and records when the latest successful load arrived.
- **Overdue Socios stay in the copy.** Their attendance and participation history is kept; only the ranking excludes them until their fees are up to date.
- **Bajas** mark the Socio inactive; nothing is deleted.
- **Stale data**: if the latest successful load is older than the configured limit (default 24 h), the ranking calculation (HU-25) and segmentation (HU-36) warn the Admin before running.
- **Volume**: up to 500,000 Socios.

## 2. Events (sent by the club, HU-21)

From the club (read-only): `id_externo` (unique per club), `titulo`, `descripcion` (optional), `fecha_hora` (ISO 8601 with offset), `lugar`, `tipo` (`Partido` / `Institucional`).
Set by the Admin (HU-22, or when confirming a historical event): class (only for "Partido") or points (only for "Evento institucional/amateur").
Kept by the system: state, received at, last updated at, published at, cancelled by the club (flag).

Event types (closed catalog):

1. **Partido**: counts in the attendance pillar and needs a class (A/B/C). Takes part in wave segmentation.
2. **Evento institucional/amateur** (wire value `Institucional`; elections and assemblies included): counts in the institutional pillar. Has no class and no waves. Its points, a whole number from 1 to 100, are defined by whoever publishes it and cannot change after publication.

History is a state, not a type: past events are sent through the historical endpoint and become `historical`.

## 3. Attendance (HU-24)

The club sends it per event, identified by the event's `id_externo`, as numbered pages. Each record:

| Field | Required | Meaning |
|---|---|---|
| `dni` | Yes | Socio who attended the event |
| `numero_socio` | No | Cross-check: if present it must belong to the same Socio as the DNI |

One record per Socio. Applies to both event types.

The CSV file used as fallback has the same columns plus `fecha_evento` (optional ISO date; if present it must equal the date of the selected event, which catches a file loaded on the wrong event). UTF-8 (BOM accepted), one header row, at most 10 MB and 100,000 rows.

## 4. Recurring institutional activities (HU-24)

The club sends the records changed since its last successful send (the first send covers the last 365 days). Each record, and each row of the CSV fallback (UTF-8, BOM accepted, one header row, at most 10 MB and 100,000 rows), has `dni`, `tipo`, `fecha_desde`, `fecha_hasta`, all required.

- `tipo` is `deporte_federado` (10 points per month) or `subcomision` (15 points per month). Elections and assemblies are not records: they are events (section 2).
- ISO dates (`YYYY-MM-DD`), not in the future, `fecha_hasta` on or after `fecha_desde`; months are counted from the range.
- Upsert key: `dni`, `tipo`, `fecha_desde`.

## 5. Integration API (exposed by the system, called by the club)

| Data | Story | Endpoint | Behavior |
|---|---|---|---|
| Socio roster, full load | HU-43 | `POST /api/v1/socios/cargas/completa` | numbered pages (`carga_id`, `pagina`, `total_paginas`); staged; activated atomically on the last page |
| Socio roster, changes | HU-43 | `POST /api/v1/socios/cargas/incremental` | batch (`lote_id`, `desde`, `hasta`) of `alta` / `modificacion` / `baja`; valid changes applied |
| Roster load status, freshness | HU-43 | `GET /api/v1/socios/cargas/{carga_id}`, `GET /api/v1/socios/freshness` | counts, rejections, age of the copy |
| One upcoming event | HU-21 | `POST /api/v1/eventos` | `201`; `409` if `id_externo` exists |
| Upcoming events | HU-21 | `POST /api/v1/eventos/batch` | `207` with created, omitted and failed |
| Historical events | HU-21 | `POST /api/v1/eventos/historicos/batch` | `207`; no 48-hour rule |
| Event update and cancellation | HU-21, HU-23 | to be added, keyed by `id_externo` | pending event: applied (HU-21); published event: omitted in the MVP, `pending review` with HU-23 |
| Club's events | HU-21 | `GET /api/v1/eventos` | filters by `id_externo`, `titulo` |
| Attendance of an event | HU-24 | to be added, paged like the roster full load | per-record rejection; replacement waits for the Admin's approval |
| Recurring activities | HU-24 | to be added, batched like the roster changes | per-record rejection; valid records applied |

- **Authentication**: `Authorization: Bearer <token>`, one token per club, shared by every endpoint. Tokens are stored hashed and never appear in logs or error messages. A missing, malformed or unknown token gets `401` and changes nothing.
- **Structure first, records second**: a request that breaks the schema is rejected whole and changes nothing. Inside a valid request, each record is validated on its own: invalid records are rejected and listed, valid ones are processed.
- **Rejection detail**: `{"id_externo" | "dni", "field", "codigo", "motivo"}`, returned in the response and kept with the load for the Admin.
- **Idempotency**: by `carga_id` + page, by `lote_id`, and by event `id_externo`. Resending the same content returns the original result; different content under the same id gets `409 CONFLICT`.
- **Error body**: `{"error": {"code": "...", "message": "...", "field": "..."}}`.
- **Times**: ISO 8601 with an explicit offset; stored in UTC.
- **Size limits**: up to 10,000 records per page or batch and 10 MB per request (`413` above). A paged load (roster full load, attendance) must receive all its pages within 60 minutes of the first one; otherwise it ends `failed` (`LOAD_EXPIRED`) and nothing is applied.
- **Watermarks**: an incremental batch (roster changes, activities) is accepted only if its `desde` is not later than the `hasta` of the last successful batch of the same kind (`WATERMARK_GAP` otherwise), so no change falls in a gap.

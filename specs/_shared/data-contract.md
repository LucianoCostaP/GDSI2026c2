# Data Contract (inputs from the club)

The system never edits Socio personal data (it is outside the product scope). The club pushes roster data to platform-provided endpoints through HU-43, and pushes events (HU-21), attendance and recurring activities (HU-24) through platform-provided endpoints. The platform does not call or pull from club APIs. The only data the Administrador enters is the class or the points of an event, and the CSV file used as fallback for HU-24.

## 1. Socio reference data (read-only copy, pushed by the club)

| Field | Used by |
|---|---|
| `id_externo` (stable, unique club identifier) | roster upsert and baja identity |
| `dni` (unique, numeric) | identification, tiebreak (lower document number), attendance and participation records |
| `numero_socio` (unique) | identification |
| `nombre` (full name) | display |
| `email` (registered, valid format) | OTP and activation codes |
| `fecha_nacimiento` | age E (P_antigüedad, tiebreak) |
| `fecha_alta` | seniority T, new-member bonus t |
| `fecha_baja_previa` (nullable) | new-member bonus (re-entry filter) |
| `estado_cuota` (`al_dia` / `moroso`) and last synchronized timestamp | HU-01, ranking eligibility, wave segmentation |
| `distancia_km` from the Socio's home to the club stadium | P_distancia |
| `localidad` (optional; no exact address) | optional display/analysis |
| `fecha_modificacion` on incremental changes | delta synchronization and audit |

Rules:

- **Venue model**: every event of type "Partido" takes place at the club stadium, so one distance per Socio is enough. Events held at other venues are registered as "Evento institucional/amateur" and score as institutional events.
- **Source of truth**: the club. The system keeps a synchronized copy and records when it was last updated.
- **Overdue Socios stay in the copy.** Their attendance and participation history is kept; only the ranking excludes them until their fees are up to date.
- **Stale data**: if the last successful synchronization is older than the configured limit (default 24 h), the ranking calculation (HU-25) and segmentation (HU-36) warn the Administrador before running.
- **Volume**: up to 500,000 Socios.
- **Push schema**: field names and load envelopes follow the [Socios API contract](../../docs/socios-api-contract.md). Full snapshots use paged chunks and incremental deliveries use stable external IDs and agreed watermarks.

## 2. Events (pushed by the club)

From the club (read-only): `id_externo` (unique club event reference), title, date/time, venue, type (`Partido` or `Institucional` on the wire; `Institucional` is presented as institutional/amateur in product language), and optional description. The platform assigns `id_interno`.
Set by the Administrador (HU-22, or at a historical import): class (only for "Partido") or points (only for "Evento institucional/amateur").
Kept by the system: state, imported at, last refreshed at, published at.

Event types (closed catalog):

1. **Partido**: counts in the attendance pillar and needs a class (A/B/C). Takes part in wave segmentation.
2. **Evento institucional/amateur** (elections and assemblies included): counts in the institutional pillar. Has no class and no waves. Its points, a whole number from 1 to 100, are defined by whoever publishes it and cannot change after publication in the MVP.

## 3. Attendance (HU-24)

The club pushes it for an event identified by the club event reference to a platform-provided endpoint. The CSV file used as fallback has the same data: UTF-8 (BOM accepted), one header row.

| Column | Required | Meaning |
|---|---|---|
| `dni` | Yes | Socio who attended the selected event |
| `numero_socio` | No | Cross-check: if present it must belong to the same Socio as the DNI |
| `fecha_evento` | No | ISO date; if present it must equal the date of the selected event (catches a file loaded on the wrong event) |

One row per Socio. Applies to both event types.

## 4. Recurring institutional activities (HU-24)

The club pushes them, including changes since the last successful delivery. The CSV file used as fallback has the same data: UTF-8 (BOM accepted), one header row, columns `dni`, `tipo`, `fecha_desde`, `fecha_hasta`, all required.

- `tipo` is `deporte_federado` (10 points per month) or `subcomision` (15 points per month). Elections and assemblies are not records: they are events (section 2).
- Both dates are required; months are counted from the range.
- ISO dates (`YYYY-MM-DD`).
- Upsert key: `dni`, `tipo`, `fecha_desde`.

## 5. Club-to-platform integration, shared by HU-43, HU-21 and HU-24

| Data | Story | Club push |
|---|---|---|
| Socio reference data | HU-43 | full paged roster initially, then incremental changes (or full roster if delta unavailable) |
| Events | HU-21 | upcoming events and historical events; updates by external event reference |
| Attendance | HU-24 | attendance records for an event, identified by club event reference |
| Recurring activities | HU-24 | activity records and changes since last successful delivery |

- The platform exposes authenticated endpoints for club-initiated pushes. Credentials are secrets and may be scoped by data type.
- Large payloads are paged/chunked and validated against the agreed request schema; an unexpected structure fails safely instead of loading bad data.
- Invalid credentials, malformed payloads, or interrupted critical deliveries never corrupt the last valid copy and are reported to administrators.


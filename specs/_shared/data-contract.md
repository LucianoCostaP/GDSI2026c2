# Data Contract (inputs from the club)

The system never edits Socio personal data (it is outside the product scope). It reads the data below from the club API through HU-N2 (Club Reference Data Sync) and also takes events (HU-21), attendance and recurring activities (HU-24) from it. The only data the Administrador enters is the class or the points of an event, and the CSV file used as fallback for HU-24.

## 1. Socio reference data (read-only, from the club API)

| Field | Used by |
|---|---|
| DNI (unique, numeric) | identification, tiebreak (lower document number), attendance and participation records |
| Member number (unique) | identification |
| Full name | display |
| Registered email | OTP and activation codes |
| Date of birth | age E (P_antigüedad, tiebreak) |
| Alta date | seniority T, new-member bonus t |
| Date of previous baja (nullable) | new-member bonus (re-entry filter) |
| Fee status (up to date / overdue) and the date it was last synchronized | HU-01, ranking eligibility, wave segmentation |
| Distance in km from the Socio's home to the club stadium | P_distancia |

Rules:

- **Venue model**: every event of type "Partido" takes place at the club stadium, so one distance per Socio is enough. Events held at other venues are registered as "Evento institucional/amateur" and score as institutional events.
- **Source of truth**: the club. The system keeps a synchronized copy and records when it was last updated.
- **Overdue Socios stay in the copy.** Their attendance and participation history is kept; only the ranking excludes them until their fees are up to date.
- **Stale data**: if the last successful synchronization is older than the configured limit (default 24 h), the ranking calculation (HU-25) and segmentation (HU-36) warn the Administrador before running.
- **Volume**: up to 500,000 Socios.

## 2. Events (imported from the club API)

From the club (read-only): club event reference (unique), date, time, venue, type.
Set by the Administrador (HU-22, or at a historical import): class (only for "Partido") or points (only for "Evento institucional/amateur").
Kept by the system: state, imported at, last refreshed at, published at.

Event types (closed catalog):

1. **Partido**: counts in the attendance pillar and needs a class (A/B/C). Takes part in wave segmentation.
2. **Evento institucional/amateur** (elections and assemblies included): counts in the institutional pillar. Has no class and no waves. Its points, a whole number from 1 to 100, are defined by whoever publishes it and cannot change after publication in the MVP.

## 3. Attendance (HU-24)

The club API provides it for an event identified by the club event reference. The CSV file used as fallback has the same data: UTF-8 (BOM accepted), one header row.

| Column | Required | Meaning |
|---|---|---|
| `dni` | Yes | Socio who attended the selected event |
| `numero_socio` | No | Cross-check: if present it must belong to the same Socio as the DNI |
| `fecha_evento` | No | ISO date; if present it must equal the date of the selected event (catches a file loaded on the wrong event) |

One row per Socio. Applies to both event types.

## 4. Recurring institutional activities (HU-24)

The club API provides them filtered by modification date. The CSV file used as fallback has the same data: UTF-8 (BOM accepted), one header row, columns `dni`, `tipo`, `fecha_desde`, `fecha_hasta`, all required.

- `tipo` is `deporte_federado` (10 points per month) or `subcomision` (15 points per month). Elections and assemblies are not records: they are events (section 2).
- Both dates are required; months are counted from the range.
- ISO dates (`YYYY-MM-DD`).
- Upsert key: `dni`, `tipo`, `fecha_desde`.

## 5. Club API (read-only), shared by HU-N2, HU-21 and HU-24

| Data | Story | Request |
|---|---|---|
| Socio reference data | HU-N2 | all Socios the first time, then changed since the last run |
| Events | HU-21 | upcoming not yet imported; past by date range for the history |
| Attendance | HU-24 | for one event, by club event reference |
| Recurring activities | HU-24 | changed since the last load |

- One API client and one credential (a secret) serve the three stories.
- Responses are paginated and validated against an expected schema; an unexpected change fails the request instead of loading bad data.
- Failures (unavailable, timeout, unauthorized) never change data and are reported on screen.


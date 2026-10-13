# Data Contract (inputs from the club)

The system never edits Socio personal data (it is outside the product scope). It reads the data below from the club's systems through HU-N2 (Club Reference Data Sync) and loads event-related data through HU-21, HU-24 and HU-N1.

## 1. Socio reference data (read-only, from the club)

| Field | Used by |
|---|---|
| DNI (unique, numeric) | identification, tiebreak (lower document number), attendance and participation files |
| Member number (unique) | identification |
| Full name | display |
| Registered email | OTP and activation codes |
| Date of birth | age E (P_antigüedad, tiebreak) |
| Alta date | seniority T, new-member bonus t |
| Date of previous baja (nullable) | new-member bonus (re-entry filter) |
| Fee status (up to date / overdue) and the date it was last synchronized | HU-01, ranking population, wave segmentation |
| Distance in km from the Socio's home to the club stadium | P_distancia |

Rules:

- **Single stadium**: the model assumes all official events take place at the club stadium, so one distance per Socio is enough. [NEEDS CLARIFICATION: events at other venues.]
- **Source of truth**: the club. The system keeps a synchronized copy and records when it was last updated.
- **Stale data**: if the last successful synchronization is older than the configured limit (default 24 h), the ranking calculation (HU-25) and segmentation (HU-36) warn the Administrador before running.

## 2. Events (loaded in the system)

Event: date, time, venue, type, class (A/B/C), capacity (tickets/seats available to Socios), state, base-information-loaded-at, published-at. See HU-21 and HU-22.

## 3. Attendance (HU-24)

CSV, UTF-8 (BOM accepted), one header row, one required column `dni`. One row per Socio who attended the selected event.

## 4. Institutional participation (HU-N1)

CSV, UTF-8, one header row, columns `dni`, `tipo`, `fecha_desde`, `fecha_hasta`.

- `tipo` is one of `eleccion`, `asamblea`, `deporte_federado`, `subcomision`.
- Civic events (`eleccion`, `asamblea`) use only `fecha_desde` (the event date); `fecha_hasta` stays empty.
- Activities (`deporte_federado`, `subcomision`) use both dates; months are counted from the range.
- ISO dates (`YYYY-MM-DD`).

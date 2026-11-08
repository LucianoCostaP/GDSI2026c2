# Feature Specification: Automatic Wave Schedule Generation

**Feature Branch**: `hu-37-wave-schedule-generation`
**Created**: 2026-10-11 | **Revised**: 2026-11-07 (v5)
**Status**: Draft
**Backlog Reference**: HU-37 (Estimate: 3, Priority: Alta, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an Admin, I want to automatically generate the enablement dates of each segmented wave, so that I define when reservation access opens for each group of Socios without assigning dates one by one."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automatic Wave Schedule Generation (Priority: P1)

As an Admin, I want to automatically generate the enablement dates of each segmented wave, so that I define when reservation access opens for each group of Socios without assigning dates one by one.

**Why this priority**: Turns the segmentation into a timeline that Socios can follow.

**Independent Test**: With an existing segmentation, define opening and closing and verify start dates are evenly spaced, best-ranked wave first, and shown to the Admin.

**Acceptance Scenarios**:

1. **Given** an event without segmentation, **When** the Admin tries to generate the schedule, **Then** it is not possible, as it requires an existing segmentation (HU-36).
2. **Given** an existing segmentation, **When** the Admin defines the total reservation period (opening of the first wave and general closing, date and time), **Then** the period is validated and accepted.
3. **Given** a defined period, **When** the schedule is generated, **Then** wave i starts at `opening + (i − 1) × (closing − opening) / N`, in order, wave 1 (the best positions of the ranking) first.
4. **Given** a generated schedule, **When** the Admin reviews it, **Then** they see each wave with its start time, the closing time and the number of Socios, and must confirm it before Socios can see it.
5. **Given** a wave that reaches its start date/time, **When** it is enabled, **Then** access stays open for that wave and all previous ones until the general closing.
6. **Given** a confirmed schedule, **When** the first wave has not opened, **Then** the Admin may regenerate it after a confirmation, replacing the previous schedule.
7. **Given** the first wave has opened, **When** the Admin tries to regenerate, **Then** it is blocked.

---

### Edge Cases

- **Invalid period**: the opening must be in the future, the closing after the opening, the closing not after the event start, and the step between waves at least the minimum (default 5 minutes). Otherwise the period is rejected with the reason.
- **Fewer waves**: waves with no Socios (very small rankings) are omitted by HU-36; the schedule covers only the waves that exist.
- **Only for Partido events**: institutional/amateur events have no waves.
- **Segmentation regenerated** (HU-36): the schedule is invalidated and must be generated again.
- **Scope of "access"**: in the MVP the schedule is informative. The club's external ticketing platform manages availability and purchase; this system does not take or enforce reservations (HU-40 is outside the MVP).
- **Boundaries of the period**: the opening must be strictly after now; a closing equal to the event start is accepted ("not after"). The minimum step is checked as `closing − opening ≥ N × minimum` (no rounding). When several rules fail, only the first one is reported, in this order: opening in the future, closing after opening, closing not after the event start, minimum step.
- **Input time zone**: dates are sent as ISO-8601 with offset; a date without offset is read in America/Argentina/Buenos_Aires (cross-cutting section 1).
- **Stale draft**: a draft can only be confirmed while its opening is still in the future; otherwise it must be regenerated.
- **Regenerating a confirmed schedule** returns it to `draft`: Socios stop seeing it until the Admin confirms again.
- **First wave opened** means a `confirmed` schedule whose opening has passed. A draft past its opening does not lock regeneration (Socios never saw it).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST only generate a schedule over an existing, valid segmentation.
- **FR-002**: System MUST let the Admin define the total reservation period (first wave opening and general closing date/time).
- **FR-003**: System MUST distribute wave start times evenly within the period, in order, with wave 1 (the best positions of the ranking) first.
- **FR-004**: System MUST define that access for a wave and all previous waves stays open from the wave's start until the general closing.
- **FR-005**: System MUST validate the period as described in the edge cases.
- **FR-006**: System MUST show the generated schedule to the Admin and require confirmation before it is visible to Socios.
- **FR-007**: System MUST block regeneration once the first wave opened.
- **FR-008**: System MUST audit generation and confirmation.

### Key Entities

- **WaveSchedule**: event, segmentation, opening, closing, status (`draft` / `confirmed` / `invalidated`), generated at/by, confirmed at/by. Wave start times are derived, not stored.
- **Wave**: as in HU-36, plus enablement date/time.

## API

Admin only. The club always comes from the Admin's account, as in HU-36.

| Method and path | Body | Response |
|---|---|---|
| `GET /admin/events/{event_id}/schedule` | — | `200 WaveScheduleOut` |
| `POST /admin/events/{event_id}/schedule` | `{ opening_at, closing_at, confirmed = false }` | `201` created as `draft` · `200` replaced (requires `confirmed`) |
| `POST /admin/events/{event_id}/schedule/confirm` | — | `200 WaveScheduleOut` (`confirmed`) |

`WaveScheduleOut`: `event { id_interno, titulo, fecha_hora, lugar }`, `status` (`draft` / `confirmed` / `invalidated`), `opening_at`, `closing_at`, `step_seconds`, `min_step_minutes`, `locked` (first wave opened), `generated_at`, `generated_by`, `confirmed_at`, `confirmed_by`, `waves [{ order, percentile_from, percentile_to, position_from, position_to, socios, starts_at, state }]`, with `state` in `pending` / `open` / `closed`.

The list of upcoming Partidos of HU-36 (`GET /admin/segmentation/events`) adds `schedule: { status, opening_at, closing_at } | null` to each item, and the waves of a Partido (`GET` and `POST /admin/events/{event_id}/segmentation`) add `min_step_minutes`, so the Admin sees the minimum before a schedule exists.

### Errors

| HTTP | Code | Message |
|---|---|---|
| 404 | `EVENT_NOT_FOUND` | No encontramos el evento. |
| 409 | `EVENT_NOT_PUBLISHED` | El evento todavía no está publicado: publicalo antes de armar el cronograma. |
| 409 | `NOT_A_PARTIDO` | Las olas son solo para partidos: este evento no es un partido. |
| 409 | `EVENT_ALREADY_STARTED` | El partido ya empezó: no se puede generar el cronograma. |
| 409 | `SEGMENTATION_REQUIRED` | Este partido todavía no tiene olas: generalas antes de armar el cronograma. |
| 422 | `OPENING_NOT_IN_FUTURE` | La apertura tiene que ser posterior a este momento. |
| 422 | `CLOSING_NOT_AFTER_OPENING` | El cierre tiene que ser posterior a la apertura. |
| 422 | `CLOSING_AFTER_EVENT_START` | El cierre no puede ser posterior al inicio del partido. |
| 422 | `WAVE_STEP_TOO_SHORT` | Entre oleadas tiene que haber al menos {m} minutos: con {N} oleadas, el período tiene que durar al menos {N·m} minutos. |
| 422 | `CONFIRMATION_REQUIRED` | Este partido ya tiene un cronograma. Confirmá para reemplazarlo. |
| 409 | `SCHEDULE_LOCKED` | La primera ola ya abrió: no se puede regenerar el cronograma. |
| 404 | `SCHEDULE_NOT_FOUND` | Este partido todavía no tiene cronograma. |
| 409 | `SCHEDULE_ALREADY_CONFIRMED` | El cronograma ya está confirmado. |
| 409 | `SCHEDULE_INVALIDATED` | Las olas se regeneraron: generá el cronograma de nuevo. |
| 409 | `OPENING_ALREADY_PASSED` | La apertura ya pasó: regenerá el cronograma con otro período. |

Audit (`entity = "wave_schedule"`): `wave_schedule.generated`, `wave_schedule.regenerated` (with `previous`), `wave_schedule.confirmed`, `wave_schedule.invalidated`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of waves of a segmentation get an enablement date within the period.
- **SC-002**: Start dates are in percentile order and equally spaced (a parity test checks the formula).
- **SC-003**: 0 draft or invalidated schedules are visible to Socios.

## Assumptions

- "Equitable" means evenly spaced starts beginning at the opening, as in the formula above.
- Notifications of the schedule are outside the MVP (HU-19/20).
- A time zone is fixed (cross-cutting section 1).

## Revision Notes (v2)

- Defined the formula, validations, draft/confirm visibility, regeneration limits, and stated that access is informative in the MVP.
- v3: only for Partido events; empty waves omitted.
- v4: API contract, error codes and messages; period boundaries and rule order; input time zone; stale drafts; regenerating a confirmed schedule returns it to draft; definition of "first wave opened".
- v5: wave state (`pending` / `open` / `closed`) only for confirmed schedules; `locked` in the response; regenerating the waves (HU-36) invalidates the schedule and a new one needs no confirmation; schedule summary in the HU-36 list; `EVENT_NOT_PUBLISHED` for a Partido pending publication; `min_step_minutes` in the HU-36 waves response.

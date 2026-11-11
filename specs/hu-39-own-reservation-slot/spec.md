# Feature Specification: View Own Assigned Slot

**Feature Branch**: `hu-39-own-reservation-slot`
**Created**: 2026-10-11 | **Revised**: 2026-11-08 (v4)
**Status**: Draft
**Backlog Reference**: HU-39 (Estimate: 2, Priority: Alta, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Socio of the club, I want to consult the date and time at which my own reservation access opens, so that I know from when I can reserve my turn for that event."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Own Assigned Slot (Priority: P1)

As a Socio of the club, I want to consult the date and time at which my own reservation access opens, so that I know from when I can reserve my turn for that event.

**Why this priority**: Without it the wave schedule has no practical effect for the Socio.

**Independent Test**: With a confirmed schedule, view the screen as Socios from different waves and verify the wave, the date and time, and each of the states: before, open, closed, not in a wave, no schedule.

**Acceptance Scenarios**:

1. **Given** a Socio included in a segmentation with a confirmed schedule, **When** they open the screen for an event (from HU-17), **Then** they see the wave they belong to (derived from their position in the ranking version the segmentation is built on) with its enablement date and time.
2. **Given** the wave's enablement time has passed and the general closing has not, **When** the Socio opens the screen, **Then** they are told access is already enabled and until when (the general closing).
3. **Given** the wave is not enabled yet, **When** the Socio opens the screen, **Then** they are told how much time remains, computed from the server clock.
4. **Given** the general closing has passed, **When** the Socio opens the screen, **Then** they are told the reservation period is closed.
5. **Given** the event has a segmentation but the Socio is not in any wave (joined or became up to date after the ranking version the segmentation is built on), **When** they open the screen, **Then** they are told that no turn was assigned and that they should contact the club.
6. **Given** the event has no confirmed schedule, **When** the Socio opens the screen, **Then** they are informed that the schedule is not defined yet, instead of seeing an empty screen.
7. **Given** a Socio who was not in the ranking behind the segmentation because their fees were overdue when it was calculated, **When** they open the screen, **Then** they get the message of scenario 5.
   A Socio who became overdue **after** that ranking keeps their wave: the segmentation is not recalculated with later fee changes.
8. **Given** an event of type Evento institucional/amateur, **When** the Socio opens the screen, **Then** they are told that this event has no turns.

---

### Edge Cases

- **Read-only**: nothing on this screen is editable.
- **The wave is fixed**: it derives from the ranking version of the segmentation, which is immutable, so later recalculations do not move the Socio between waves.
- **Access meaning**: "enabled" is informative; purchase happens on the club's external ticketing platform.
- **Excluded by seat transfer**: not applicable in the MVP (the transfer feature is not in scope).
- **Order of the checks**: institutional/amateur event → no turns; no `confirmed` schedule (none, `draft` or `invalidated`, or a Partido without segmentation) → not defined; general closing passed → closed (for every Socio, with or without a wave); Socio without an entry in the segmentation's ranking version → no turn assigned; otherwise the wave is `pending` or `open`.
- **Overdue fees now do not matter**: unlike HU-14, the current `estado_cuota` is not read. Only the entry in the segmentation's ranking version counts (the ranking population already left out the Socios with overdue fees at calculation time, scenario 7).
- **Account without a roster Socio** (no Socio of the club with the account's DNI): treated as no turn assigned.
- **Event not visible**: an event that does not exist, belongs to another club or is not `published` returns 404, as an unknown event.
- **Live countdown**: the server sends the seconds left. The screen counts them down with its own timer, never reading the device date, and asks the server again when they reach zero (the wave goes to open, or the period closes). Shown as days, hours and minutes, without seconds; under one minute it reads "Falta menos de un minuto".
- **What the Socio sees**: the event (title, date, time, venue), "Ola N de M" and the enablement date and time. Neither the position nor the percentile is shown, since they would be confused with the current position of HU-14.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST show the Socio's wave, as derived from the segmentation, with its enablement date and time.
- **FR-002**: System MUST tell the Socio access is already enabled and until when, if the wave's time has passed and the period is open.
- **FR-003**: System MUST tell the Socio how much time remains if the wave is not enabled yet.
- **FR-004**: System MUST tell the Socio when the reservation period has closed.
- **FR-005**: System MUST handle a Socio outside the segmentation and an event with no confirmed schedule with explanatory messages.
- **FR-006**: System MUST present the information as read-only.

### Key Entities

- **Wave** and **WaveSchedule**: as in HU-36 and HU-37, consulted per Socio.

## API

Socio only. The club comes from the Socio's account; a `club_id` parameter is ignored (cross-cutting section 9). Like HU-17, it accepts the test clock (`X-Test-Clock` header or `reloj_simulado` query), ignored in production.

| Method and path | Response |
|---|---|
| `GET /member/events/{event_id}/slot` | `200 OwnSlotOut` · `404 EVENT_NOT_FOUND` |

`event_id` is the `id_interno`, the same one used by `slot_url` in HU-17.

`OwnSlotOut`:

| Field | Value |
|---|---|
| `event` | `{ id_interno, titulo, fecha_hora, lugar, tipo }` |
| `status` | `no_turns` · `no_schedule` · `no_wave` · `pending` · `open` · `closed` |
| `message` | Text for `no_turns`, `no_schedule`, `no_wave` and `closed`; `null` otherwise |
| `wave` | `{ order, total }` when the Socio has a wave; `null` otherwise |
| `starts_at` | Start of the Socio's wave (UTC), when they have one |
| `closing_at` | General closing (UTC), when there is a confirmed schedule |
| `seconds_until_start` | Only in `pending` |
| `seconds_until_closing` | Only in `pending` and `open` |
| `now` | Server time used for the answer (UTC) |

Messages:

| Status | Message |
|---|---|
| `no_turns` | "Este evento no tiene turnos de reserva." |
| `no_schedule` | "El cronograma de reservas de este evento todavía no está definido." |
| `no_wave` | "No tenés un turno asignado para este evento. Contactá al club." |
| `closed` | "El período de reserva de este evento terminó." |

In `pending` and `open` the screen writes the text with the dates in Buenos Aires time: "Tu acceso a la reserva se habilita el {fecha} a las {hora}" and "Tu acceso a la reserva ya está habilitado hasta el {fecha} a las {hora}", followed by a note that the purchase is made on the club's ticketing platform.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of included Socios see the wave and enablement time matching the confirmed schedule.
- **SC-002**: 100% of Socios outside any wave see the explanation instead of a wave.
- **SC-003**: Countdowns use the server clock; a test with a skewed device clock shows the same value.

## Assumptions

- The Socio reaches this screen from the events list (HU-17).

## Revision Notes (v2)

- Added the closed, not-in-wave and no-schedule states, server-clock countdown and the link from HU-17.
- Replaced the non-testable "excluded by transfer" case with the real "outside the segmentation" case.
- v3: wave derived from the ranking version; added the no-turns state for institutional events.
- v4: scenario 5 refers to the ranking version, as in the backlog; added the order of the checks, the live countdown, what the screen shows and the API.

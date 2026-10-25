# Feature Specification: Receive Events Sent by the Club

**Feature Branch**: `hu-21-club-event-reception`
**Created**: 2026-10-11 | **Revised**: 2026-10-25 (v4)
**Status**: Draft
**Backlog Reference**: HU-21 (Estimate: 5, Priority: Alta, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md)
**Input**: "As an Admin, I want the system to offer an integration interface (API/endpoints) for the club to send upcoming and historical events (date, time, venue, type), so that they are incorporated into the platform automatically and I can later define their category (class A/B/C) or their points."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Receive Events Sent by the Club (Priority: P1)

The club organizes the events and is the source of truth. It **sends** them to endpoints the system exposes; the system never calls the club. The Admin adjusts only the scoring parameters: the class of a Partido or the points of an institutional/amateur event (HU-22).

**Why this priority**: First step of the event lifecycle: no event can be published, segmented or scored until it exists in the system.

**Independent Test**: With the club token, send a batch with one valid upcoming Partido, one starting in less than 48 hours, one with a missing venue and one already sent. Verify the `207` report (created, omitted, failed with reason), that the valid one is `pending importance definition` with its reception time and publication deadline, and that it does not appear in the Socio events list.

**Acceptance Scenarios**:

1. **Given** the club has a valid integration token, **When** it sends one event or a batch of upcoming events with their external id (`id_externo`), title, date and time, venue and type (Partido or Evento institucional/amateur), **Then** each valid event that does not exist yet is registered automatically in state `pending importance definition`, keeping the club's data and the reception time.
2. **Given** a registered upcoming event, **When** the Admin opens the received events, **Then** they see it with the time left to complete its publication within the deadline of HU-22.
3. **Given** a registered event, **When** a Socio opens the events list (HU-17), **Then** the event is not visible.
4. **Given** an event sent by the club, **When** the Admin looks at its date, time, venue and type, **Then** they are read-only, to stay faithful to the official source. The Admin can only define the class of a Partido or the points of an institutional/amateur event (HU-22).
5. **Given** an event already registered and published, **When** the club sends it again, **Then** it is not duplicated: the batch reports it as omitted (a single-event send answers `409 CONFLICT`).
6. **Given** an event still in `pending importance definition`, **When** the club sends an update of it (same `id_externo`), **Then** its date, time and venue are updated with the club's data, and the deadline to publish it is neither restarted nor changed.
7. **Given** an upcoming event whose start is less than 48 hours after its reception, **When** the club sends it, **Then** it is rejected, never registered: the API answers `422` with the code `INSUFFICIENT_LEAD` and the reason, and the rejection appears in the Admin's reception log. There is no "registered as non-publishable" alternative.
8. **Given** an update of a pending event that would make it start less than 48 hours from now, **When** it is received, **Then** the change is not applied, the Admin is informed, and they can choose to discard the event.
9. **Given** an event without valid or complete date, time, venue or type, **When** the club sends it, **Then** the API rejects it with the validation reason and no incomplete record is created; in a batch, the other events are processed normally.
10. **Given** an event in `pending importance definition`, **When** the club sends its cancellation, **Then** the Admin is informed, the automatic publication of HU-22 is withheld, and the Admin can discard it (state `discarded`): it is never visible to Socios (HU-17) and never scored.
11. **Given** events whose start already passed, **When** the club sends them through the historical endpoint, **Then** they are registered as `historical` without the 48-hour rule, never published and never visible to Socios. The Admin defines the class of each Partido and the points of each institutional/amateur event, prefilled with the defaults (Clase B, 20 points), and confirms them; once confirmed they accept attendance (HU-24).
12. **Given** a request without a valid token, **When** it is received, **Then** it is rejected with `401 UNAUTHORIZED` and no data changes. The token never appears in logs or error messages.
13. **Given** any reception, update, validation rejection, discard or historical registration, **When** it happens, **Then** it is recorded in the audit log.

---

### Edge Cases

- **Types**: **Partido** (counts in the attendance pillar, needs a class, takes part in waves) or **Evento institucional/amateur** (counts in the institutional pillar, has no class and no waves; its points are set at publication, also for elections and assemblies). Every Partido takes place at the club stadium; events held elsewhere are institutional/amateur.
- **History is a state, not a type**: an event becomes `historical` by being sent through the historical endpoint.
- **Reference**: `id_externo` is unique per club and is the key HU-24 uses to receive attendance.
- **Updates of published events**: in the MVP a resent published event is omitted (scenario 5). Reviewing and applying changes to published events, and withdrawing them, is HU-23, outside the MVP.
- **Batch results**: a batch answers `207 Multi-Status` with a summary (total, created, omitted, failed) and the detail of each event.
- **Volume**: the received events list in the admin view is paginated.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose authenticated endpoints for the club to send one upcoming event, a batch of upcoming events, and a batch of historical events, plus a query of the club's events.
- **FR-002**: System MUST register each valid new upcoming event in `pending importance definition`, with the club's data, `id_externo` and reception time.
- **FR-003**: System MUST NOT show the event to Socios at this step.
- **FR-004**: System MUST record the reception time, as it starts the publication deadline of HU-22.
- **FR-005**: System MUST keep the club's data read-only, and apply the club's updates to a pending event without restarting its deadline, unless the new start is less than 48 hours away.
- **FR-006**: System MUST reject upcoming events (of either type) starting less than 48 hours after reception, and events with incomplete or invalid data, stating the reason.
- **FR-007**: System MUST be idempotent by `id_externo`: a resent existing event is never duplicated.
- **FR-008**: System MUST flag a pending event cancelled by the club, withhold its automatic publication and let the Admin discard it.
- **FR-009**: System MUST register historical events without the 48-hour rule, and let the Admin confirm their class or points (prefilled with the defaults) before they accept attendance.
- **FR-010**: System MUST authenticate the club with the token shared with HU-43 and HU-24, stored hashed and never logged.
- **FR-011**: System MUST audit every reception, update, rejection, discard and historical registration.

### Key Entities

- **Event**: `id_externo` (unique per club), title, description (optional), start date and time, venue, type (`Partido` / `Evento institucional/amateur`), class (Partido only) or points (institutional/amateur only), class or points confirmed (historical events), state (`pending importance definition` / `published` / `historical` / `discarded`), received at, last updated at, cancelled by the club (flag).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of valid upcoming events received start in `pending importance definition` with the reception time recorded.
- **SC-002**: 0 events in `pending importance definition`, `historical` or `discarded` are visible to Socios.
- **SC-003**: 0 upcoming events are registered with a start less than 48 hours after reception.
- **SC-004**: 0 events are registered twice.

## Assumptions

- The club can call an HTTPS endpoint with a Bearer token, and sends each event before the 48-hour lead.
- Capacity is not captured: waves are percentile-based (HU-36).
- The 48-hour lead is the minimum time between publication and the event start.

## Implementation Status (prototype `API-Eventos-Pasion-de-10`)

Already implemented:

- `POST /api/v1/eventos` (single event: `201`, `409` if `id_externo` exists, `422` if a Partido starts in less than 48 hours, `400` on missing or invalid fields), `POST /api/v1/eventos/batch` (`207` with `creados`, `omitidos` and `fallidos`; rejects past events; omits duplicates), `POST /api/v1/eventos/historicos/batch` (`207`, no 48-hour rule, state `Historico`), `GET /api/v1/eventos` (filters by `id_externo`, `id_interno`, `titulo`).
- Payload: `id_externo`, `titulo`, `fecha_hora` (ISO 8601), `lugar`, `tipo`, `descripcion`, `es_historico`. Events are stored in `pendiente_definicion_importancia`, never visible directly.
- Bearer token per club; multi-tenant Postgres views filtered by `app.current_club_id`.

Gaps to close when porting it to this backend:

- The 48-hour rule is only applied to Partidos; it MUST apply to institutional/amateur events too (HU-22 cannot publish them otherwise).
- A resent pending event is omitted or answered with `409`; it MUST update the pending event (scenario 6, 8).
- The cancellation of a pending event (scenario 10) is not implemented.
- `tipo` accepts `Historico`; history MUST be expressed only by the historical endpoint, and `tipo` limited to `Partido` and `Institucional`.
- Historical events are stored without class or points and without the Admin's confirmation (scenario 11); the historical endpoint does not check that the start already passed.
- Tokens are stored in plain text; they MUST be stored hashed. The error body is `{"error": "<message>", "status_code"}`; it MUST use the shared format of the data contract (as HU-43 does).
- The audit trail is not built.

## Revision Notes

- v3.4: events imported by calling the club API.
- v4: aligned with the backlog: the club sends the events (push); the Admin no longer selects events to import; updates of pending events and cancellations come from the club; historical events arrive by their own endpoint. Contract aligned with the prototype.

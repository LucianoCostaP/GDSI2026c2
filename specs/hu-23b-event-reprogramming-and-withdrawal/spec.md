# Feature Specification: Event Reprogramming and Withdrawal by the Admin

**Feature Branch**: `hu-23b-event-reprogramming-and-withdrawal`
**Created**: 2026-11-18 (v1)
**Status**: Draft (replaces HU-23, decision 62)
**Backlog Reference**: HU-23B (replaces HU-23; Estimate: to be defined, Priority: Media, MVP: No)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [notifications](../_shared/notifications.md), [data contract](../_shared/data-contract.md)
**Input**: flows given by the team (2026-11-18). Reprogramming: "que dentro de eventos del admin aparezcan todos los eventos publicados y que todavía no pasaron, y que cada evento tenga su botón de reprogramar; que se pueda modificar el tipo de partido y el día y horario; si hay solapamiento entre una o más oleadas (y todas las subsecuentes) y el horario de comienzo del partido, que todas las oleadas afectadas se muevan a la última oleada que no estaba afectada; todos los cambios se notifican al socio con las notificaciones de HU-19 y HU-20". Withdrawal: "junto a cada evento publicado que todavía no pasó, un botón 'Retirar evento' con un mensaje de confirmación; una vez confirmado, ni el socio ni el admin lo ven más; si tiene oleadas o cronograma, también se borran; a los socios se les notifica con un mensaje genérico que el evento se suspendió y que, si compraron entradas, se comuniquen con el club".

**Context**: HU-23B **replaces HU-23** (decision 62). In HU-23 the club sent a change, the Admin approved or rejected it, and a withdrawn event could be restored. HU-23B is driven by the Admin: from the list of upcoming published events, the Admin reprograms an event directly (new date and time) or withdraws it for good. The class of a Partido and the points of an institutional/amateur event stay fixed once published (HU-22). A reprogramming that moves the start before the waves (HU-36, HU-37) merges the affected waves into the last unaffected one. Every change is notified through the contract of HU-19 (notifications section 4), and the inbox of HU-20 shows it.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - List of Upcoming Published Events (Priority: P1)

As an Admin, I want to see the published events of my club that have not started, each one with its actions, so that I can find the event I need to reprogram or withdraw.

**Why this priority**: both actions start from this list.

**Independent Test**: with a published event in the future, one that already started, a withdrawn one, a pending one and one of another club, verify that only the first one is listed and that it shows both actions.

**Acceptance Scenarios**:

1. **Given** published events of the Admin's club whose start has not passed, **When** the Admin opens "Eventos publicados", **Then** they see all of them ordered by start, the nearest first, each with its title, type, date and time (Buenos Aires, `dd/mm/aaaa HH:mm`), venue, class (Partido) or points (institutional/amateur) and, for a Partido, the state of its wave schedule (none, `draft`, `confirmed`, `invalidated`, adjusted).
2. **Given** the list, **When** it renders, **Then** each event offers "Reprogramar" and "Retirar evento".
3. **Given** an event whose start has passed, a withdrawn one, one in `pending importance definition`, a `historical` or `discarded` one, or an event of another club, **When** the list renders, **Then** it is not there.
4. **Given** the club sent the cancellation of a published event (HU-23 user story 2, scenario 1), **When** the list renders, **Then** the event shows the flag "Cancelado por el club" next to its actions.
5. **Given** no published upcoming events, **When** the Admin opens the list, **Then** they see "No hay eventos publicados próximos." instead of an empty screen.
6. **Given** the start of a listed event passes while the screen is open, **When** the Admin uses one of its actions, **Then** the server rejects it with `EVENT_ALREADY_STARTED` and the list is reloaded.

---

### User Story 2 - Reprogram an Event (Priority: P1)

As an Admin, I want to change the date and time of a published event, so that the information stays correct when the club moves the event.

**Why this priority**: it is the first flow of the request.

**Independent Test**: reprogram a Partido without schedule and verify the new date in HU-17 and the notification; then reprogram a Partido with a confirmed schedule to a start that falls inside the waves and verify the merge, the new closing and the notifications to the moved Socios.

**Acceptance Scenarios**:

1. **Given** a listed event, **When** the Admin chooses "Reprogramar", **Then** they see a form prefilled with its current date and time, the only editable fields. Title, type, venue, description and the class (Partido) or points (institutional/amateur) are shown read-only.
2. **Given** the form, **When** the Admin enters a new date and time later than now and confirms, **Then** the event keeps its state `published`, takes the new start, and what Socios see (HU-17, HU-18, HU-39) reflects it immediately, with no new publication.
3. **Given** a request that tries to change the type, the class, the points or any club field (title, venue, description), **When** it reaches the server, **Then** it is rejected with `FIELD_NOT_EDITABLE` and nothing changes: the type decides how the event is scored and whether it has waves, and the class or points are fixed once published (HU-22 scenario 9, decision 62).
4. **Given** the form with the same values the event already has, **When** the Admin confirms, **Then** nothing is stored, nothing is notified, and they see "No hay cambios para guardar."
5. **Given** a new date and time that is not later than now, **When** the Admin confirms, **Then** it is rejected with `START_NOT_IN_FUTURE` and nothing changes.
6. **Given** a date and time without a valid format, **When** the Admin confirms, **Then** it is rejected with the reason and nothing changes.
7. **Given** a Partido with a segmentation (HU-36) or a schedule (HU-37), **When** the Admin fills the form with a new date and time, **Then**, before confirming, they see what will happen to the schedule (user story 3): left as it is, waves that move and into which wave, the new general closing, or the schedule invalidated. Confirming applies exactly what was shown.
8. **Given** an applied reprogramming, **When** it is stored, **Then** the audit log records who, when and the previous and new date and time, and, if it touched the schedule, the previous and new schedule values (user story 3, scenario 9).
9. **Given** two Admins reprogram or withdraw the same event at the same time, **When** the second one confirms, **Then** it fails with `EVENT_CHANGED` because the event changed after their form was loaded, and the form is shown again with the current values.
10. **Given** an applied reprogramming, **When** it commits, **Then** every Socio of the club with an `activated` account receives `event_rescheduled` with the new date and time (user story 4).

---

### User Story 3 - Wave Adjustment After a Reprogramming (Priority: P1)

As an Admin, I want the waves of a reprogrammed Partido to adjust by themselves when the new start overlaps them, so that no wave opens after the match has started and no Socio loses their turn.

**Why this priority**: without it, a moved match leaves Socios whose access opens when the match has already started, or after it.

**Definitions**: the waves keep the start times derived when the schedule was generated (HU-37: `opening + (i − 1) × (closing − opening) / N`). A wave is **affected** by a new start `S` when it has not opened yet and its start is later than `S − m`, where `m` is the minimum step between waves (`min_step_minutes`, default 5). In other words, it would open after the match starts, or less than the minimum step before it. A wave that already opened is never affected: its Socios already have access. Affected waves are always the last ones, because starts are in order.

**Independent Test**: with a confirmed schedule of 5 waves whose starts are 10:00, 11:00, 12:00, 13:00 and 14:00 and a closing of 15:00, reprogram the match to start at 12:30 and verify that waves 4 and 5 join wave 3 (start 12:00), the closing becomes 12:30, waves 1 to 3 keep their starts, and the Socios of waves 4 and 5 are notified.

**Acceptance Scenarios**:

1. **Given** a Partido without segmentation or without schedule, **When** it is reprogrammed, **Then** only the event changes.
2. **Given** a schedule whose general closing is not later than the new start (the match moved later, or earlier but still after the closing), **When** the reprogramming is applied, **Then** the schedule is left exactly as it is.
3. **Given** a schedule whose general closing is later than the new start and no wave is affected, **When** the reprogramming is applied, **Then** the general closing becomes the new start and no wave start changes.
4. **Given** a schedule where one or more waves are affected and at least one wave is not, **When** the reprogramming is applied, **Then** all the affected waves join the last unaffected wave: their Socios take its start time, the general closing becomes the new start, and the starts of the unaffected waves do not change. The Admin sees the result as "Ola k (incluye las olas k+1 a N)".
5. **Given** the last unaffected wave already opened, **When** the affected waves join it, **Then** their Socios get access immediately, until the new closing.
6. **Given** every wave is affected (none opened, and the first one would open after the new start or less than the minimum step before it), **When** the reprogramming is applied, **Then** the schedule passes to `invalidated`, the segmentation is kept, Socios see that the schedule is not defined (HU-39), and the Admin is told to generate it again (HU-37).
7. **Given** a schedule in `draft`, **When** a reprogramming overlaps its period (new start earlier than its closing), **Then** the draft is invalidated and the Admin is told to generate it again. Socios never saw it, so nobody is notified about waves.
8. **Given** a schedule already adjusted by an earlier reprogramming, **When** the match is reprogrammed again, **Then** the same rules apply on the current waves (merged waves stay merged), and a later start never splits a merge or moves the closing later. The Admin can regenerate the schedule while the first wave has not opened (HU-37), which discards every adjustment.
9. **Given** an adjustment or invalidation of the schedule, **When** it is stored, **Then** the audit log records it with the previous and new general closing and the waves merged (`wave_schedule.adjusted`, `wave_schedule.invalidated`).
10. **Given** the segmentation of the Partido, **When** a reprogramming is applied, **Then** it does not change: each Socio stays in the wave of their position in its ranking version, which only gets a different start when merged.

---

### User Story 4 - Notifications of a Reprogramming (Priority: P1)

As a Socio, I want to be told when an event I can attend changes its date or my turn changes, so that I do not miss it.

**Why this priority**: the request requires every change to be notified, and a merged wave opens earlier than the Socio expected.

**Independent Test**: reprogram a Partido so that waves 4 and 5 join wave 3, once with wave 3 still pending and once with it already open, and verify the inbox (HU-20) of a Socio of wave 1, one of wave 4 and one outside the segmentation.

**Acceptance Scenarios**:

1. **Given** an applied reprogramming, **When** it commits, **Then** every Socio of the club with an `activated` account receives `event_rescheduled`: "{titulo} cambió: ahora es el {fecha} a las {hora}." with the new date and time.
2. **Given** affected waves join a wave that has **not** opened yet, **When** the reprogramming commits, **Then** each Socio of the moved waves with an `activated` account also receives `wave_rescheduled`: "Tu turno de reserva para {titulo} cambió: se habilita el {fecha} a las {hora}." with the start of the wave they joined. When that start arrives, the wave opening job sends them `wave_opened` as to any Socio of the wave.
3. **Given** affected waves join a wave that **already opened**, **When** the reprogramming commits, **Then** each Socio of the moved waves with an `activated` account receives `wave_opened` right away ("Ya podés reservar para {titulo}. Tu acceso está habilitado hasta el {fecha} a las {hora}.", with the new closing), using the same `occurrence_key` as the job, so the job never repeats it. They do not receive `wave_rescheduled`.
4. **Given** a schedule invalidated by a reprogramming (user story 3, scenarios 6 and 7), **When** it commits, **Then** no wave notification is generated. The Socios receive `event_rescheduled` only, and receive `wave_opened` again when the new schedule is confirmed and its waves open.
5. **Given** the Socios of the unaffected waves, **When** the reprogramming commits, **Then** they receive only `event_rescheduled`. Their start did not change, and the earlier closing is the new start of the match that the notification states.
6. **Given** notifications generated before the reprogramming (`event_published`, `wave_opened`, an earlier `event_rescheduled`), **When** the Socio reads them, **Then** they keep the text they had (frozen text) and open the event as usual.
7. **Given** a failure while generating the notifications, **When** it happens, **Then** the reprogramming stays applied (notifications section 1).

---

### User Story 5 - Withdraw an Event (Priority: P1)

As an Admin, I want to withdraw a published event that will not take place, so that nobody sees it any more, its waves disappear and the Socios are told it was suspended.

**Why this priority**: it is the second flow of the request.

**Independent Test**: withdraw a Partido with a confirmed schedule whose first wave already opened, and verify that it disappears from the Admin list and from HU-17, that its segmentation and schedule no longer exist, that the wave job generates nothing for it, that the Socios receive the suspension notice, and that the withdrawal is audited.

**Acceptance Scenarios**:

1. **Given** a listed event, **When** the Admin chooses "Retirar evento", **Then** they see a confirmation that names the event and its date and explains the effects: "¿Retirar {titulo} del {fecha} a las {hora}? Los socios y la administración dejan de verlo, se borran sus olas y su cronograma, y se avisa a los socios que el evento se suspendió. Esta acción no se puede deshacer." with "Retirar evento" and "Cancelar".
2. **Given** the confirmation, **When** the Admin cancels, **Then** nothing changes.
3. **Given** the Admin confirms, **When** the withdrawal is applied, **Then** the event passes to `withdrawn` and disappears from the Admin's list of published events, from the Admin's segmentation and schedule screens (HU-36, HU-37), and from everything Socios see (HU-17, therefore HU-18, and HU-39).
4. **Given** a withdrawn Partido with a segmentation or a schedule, in any state, **When** the withdrawal is applied, **Then** both are deleted, no wave opens, and the wave opening job generates nothing for it, even if some waves had already opened.
5. **Given** a withdrawal, **When** it commits, **Then** every Socio of the club with an `activated` account receives `event_withdrawn`: title "Evento suspendido", message "{titulo}, del {fecha} a las {hora}, se suspendió. Si compraste entradas, comunicate con el club." The message is the same for every event and carries no reason.
6. **Given** a Socio who opens a withdrawn event by an old link, a notification (`event_published`, `event_rescheduled`, `wave_opened`, `event_withdrawn`) or the slot screen (HU-39), **When** it loads, **Then** they see "Este evento fue suspendido." and the app stays usable.
7. **Given** a withdrawn event, **When** the club later sends its attendance (HU-24), an update or its cancellation (HU-21, HU-23) with the same `id_externo`, **Then** it is rejected with `EVENT_WITHDRAWN` and the event stays withdrawn.
8. **Given** a withdrawn event, **When** the ranking runs (HU-25), **Then** it does not count: it is not in the frequency denominator and it has no attendance.
9. **Given** a withdrawal, **When** it is stored, **Then** the audit log records who, when, the state change and the deleted segmentation and schedule with their values (`event.withdrawn`, `wave_segmentation.deleted`, `wave_schedule.deleted`).
10. **Given** two Admins withdraw the same event at the same time, or one reprograms it while another withdraws it, **When** the second one confirms, **Then** exactly one action takes effect and the second one fails with `EVENT_CHANGED` (or `EVENT_NOT_FOUND` if it was already withdrawn); only one `event_withdrawn` is generated per Socio.
11. **Given** a failure while generating the notifications, **When** it happens, **Then** the withdrawal stays applied.

---

### Edge Cases

- **Authorization and club**: only Admins can reach these actions, and only for events of their own club; the club comes from the Admin's account (`CurrentAdminClub`, decision 34), never from a parameter or header. An event of another club answers as an unknown event (`404 EVENT_NOT_FOUND`).
- **Eligible events**: `published` events whose start has not passed, for both actions. A pending event is not reprogrammed here: its data comes from the club (HU-21), and its removal is the discard of HU-21. A `historical` or `discarded` event is not listed.
- **The start passes during the action**: the server checks the start again when the action is confirmed; if it already passed, `EVENT_ALREADY_STARTED`.
- **No lead for a reprogramming**: the 48-hour lead of HU-21 and HU-22 applies to the publication, not to a reprogramming. The Admin can move a match to a start a few hours ahead; the only bound is that the new start is later than now.
- **Only the date and time change**: the type (Partido or institutional/amateur) never changes, because it decides how attendance is scored and whether the event has waves. The class or points stay as published (HU-22 scenario 9, FR-008); there is no 24-hour adjustment window as in HU-23. Title, venue and description are club data and are not edited here (decision 62).
- **Ranking and segmentation**: a reprogramming never touches rankings or segmentations; the segmentation depends on the ranking version, not on dates.
- **Dates of the waves are kept, not recomputed**: moving the closing must not shift the start of any unaffected wave. Today the starts are derived from `opening` and `closing` (HU-37), so the schedule needs to keep the closing used to derive the starts apart from the effective closing (Key Entities).
- **Minimum step**: a wave that would have less than `min_step_minutes` of access before the match counts as affected, so every wave that stays separate keeps at least the minimum step of HU-37.
- **Wave state after a merge**: the merged waves take the state of the wave they joined (`pending` or `open`); all of them close at the new closing. HU-39 shows the Socio the start of the wave they joined and "Ola k de M", where M is the number of waves after the merge.
- **A match moved later**: the schedule stays as it is (user story 3, scenario 2), even if the period now ends long before the match. If the first wave has not opened, the Admin can regenerate the schedule (HU-37) to use the new margin.
- **Reprogramming close to the opening**: if the new start leaves the first wave affected and it has not opened, the schedule is invalidated, never shortened to a single wave.
- **Withdrawal while waves are open**: allowed. The schedule is deleted, and Socios who already had access are told only that the event was suspended. Tickets and refunds are handled by the club (the schedule is informative, HU-37).
- **Withdrawal is final**: there is no restoration and the Admin does not see withdrawn events. If the club holds the event later, it sends it again with a **new** `id_externo` (HU-21); resending the old one is rejected (`EVENT_WITHDRAWN`). The event row is kept, not deleted, so the audit, old notifications and the club's identifiers stay consistent.
- **Changes sent by the club for a published event**: the review of club changes of HU-23 does not exist any more. A change sent by the club for a published event is omitted, as in the MVP (HU-21 scenario 5), and the club informs the Admin by another channel; its cancellation of a published event is kept only as the flag of user story 1.
- **Cancellation flag**: the flag of a club cancellation is informative; the Admin decides whether to withdraw. A reprogramming clears the flag.
- **Notifications are per action**: one reprogramming generates at most one `event_rescheduled` per Socio, plus one `wave_rescheduled` or `wave_opened` for the moved Socios. Repeating the same request (double click, network retry) creates nothing new, because the occurrence key includes the id of the reprogramming.
- **Recipients**: Socios of the club with an `activated` account, excluding Socios dado de baja or not active in the roster, as every event notification (notifications section 2). For the wave notifications, only the Socios of the moved waves.
- **Accessibility**: the confirmation of a withdrawal is reachable by keyboard and "Cancelar" has the initial focus, so an accidental Enter does not withdraw the event.
- **Performance**: a reprogramming or a withdrawal answers in under 2 seconds; the notifications are generated after the commit and do not delay the answer to the Admin beyond the batches of `notify`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list, for the Admin's club, the `published` events whose start has not passed, ordered by start, with the actions "Reprogramar" and "Retirar evento".
- **FR-002**: System MUST let the Admin change the date and time of a listed event, keeping the state `published`, its class or points and every club field, without a new publication.
- **FR-003**: System MUST reject a new start that is not later than now, any attempt to change the type, the class, the points or a club field, and actions on events that are not listed.
- **FR-004**: System MUST show the Admin the effect of a reprogramming on the wave schedule before confirming it, and apply exactly that effect.
- **FR-005**: System MUST, when the new start overlaps a confirmed schedule, merge the affected waves into the last unaffected one, set the general closing to the new start and keep the starts of the unaffected waves; invalidate the schedule when every wave is affected; invalidate an overlapped draft; and leave the schedule unchanged when the closing is not later than the new start.
- **FR-006**: System MUST notify `event_rescheduled` to every activated Socio of the club when the date or time changes, `wave_rescheduled` to the Socios of the waves merged into a pending wave, and `wave_opened` to the Socios of the waves merged into an open wave, after the commit and without ever undoing the action.
- **FR-007**: System MUST let the Admin withdraw a listed event after an explicit confirmation, moving it to `withdrawn`, hiding it from Socios and from the Admin, and deleting its segmentation and schedule.
- **FR-008**: System MUST notify `event_withdrawn`, with the generic suspension message, to every activated Socio of the club after a withdrawal, without ever undoing it.
- **FR-009**: System MUST keep withdrawn events out of the scoring and reject attendance, updates and cancellations sent by the club for them.
- **FR-010**: System MUST audit every reprogramming (previous and new values), schedule adjustment or invalidation, withdrawal and deletion of a segmentation or schedule.
- **FR-011**: System MUST restrict these actions to Admins of the event's club, enforced on the server, and make them exclusive: a confirmation fails if the event changed since the form was loaded.

### Key Entities

- **Event**: as in HU-21 and HU-22, plus the state `withdrawn`, withdrawn at and withdrawn by, and a version (or last updated at) used to detect concurrent changes.
- **EventReprogramming**: event, previous and new date and time, effect on the schedule (`none`, `closing_adjusted`, `waves_merged`, `invalidated`), reprogrammed at, reprogrammed by. Its id is part of the notification keys.
- **WaveSchedule**: as in HU-37, plus the **effective closing** (the general closing after adjustments; equal to the generated closing until a reprogramming moves it) and the **last separate wave** (`merged_into_order`, empty when nothing was merged: waves after it take its start). Wave starts are still derived from the opening and the generated closing, so an adjustment never moves an unaffected wave. Regenerating the schedule (HU-37) clears both fields.

## API

Admin only. The club comes from the Admin's account (decision 34). Dates are ISO 8601 with offset; a date without offset is read in Buenos Aires (cross-cutting section 1).

| Method and path | Body | Response |
|---|---|---|
| `GET /admin/events/published` | — | `200 [PublishedEventOut]`, upcoming only |
| `POST /admin/events/{event_id}/reschedule/preview` | `{ fecha_hora }` | `200 RescheduleImpactOut` (changes nothing) |
| `POST /admin/events/{event_id}/reschedule` | `{ fecha_hora, expected_version, expected_schedule_effect?, expected_merged_into_order? }` | `200 RescheduleOut` |
| `POST /admin/events/{event_id}/withdraw` | `{ confirmed: true, expected_version }` | `200 { id_interno, estado: "withdrawn", segmentation_deleted, schedule_deleted }` |

`PublishedEventOut`: `id_interno`, `id_externo`, `titulo`, `tipo`, `fecha_hora`, `lugar`, `descripcion` (shown read-only in the form of user story 2), `clase` or `puntos`, `cancelado_por_el_club`, `version`, `schedule: { status, opening_at, closing_at (effective), merged_into_order, adjusted } | null`.
`RescheduleImpactOut`: `previous_fecha_hora`, `new_fecha_hora`, `schedule_effect` (`none` / `closing_adjusted` / `waves_merged` / `invalidated` / `no_schedule`), `previous_closing_at`, `new_closing_at`, `merged_into_order`, `moved_waves [{ order, socios }]`, `target_wave_starts_at`, `target_wave_open` (bool), `notifications { event_rescheduled, wave_rescheduled, wave_opened }` (expected number of recipients).
`expected_schedule_effect` and `expected_merged_into_order` are the effect the preview showed (user story 2, scenario 7): when they are sent and the effect is no longer the same (for example, a wave opened in between), the reprogramming fails with `EVENT_CHANGED` instead of applying another effect. `fecha_hora` is read as text, so a date and time without a valid format answers `INVALID_DATETIME` with the reason (scenario 6).
`RescheduleOut`: the event as in `PublishedEventOut` plus `id_reprogramacion` and the applied `RescheduleImpactOut`.
The schedule of HU-37 (`GET /admin/events/{event_id}/schedule`) returns the effective `closing_at`, the `generated_closing_at` the wave starts derive from, `merged_into_order` and, when `invalidated`, `invalidation_reason` (`waves_regenerated` or `event_rescheduled`).

### Errors

| HTTP | Code | Message |
|---|---|---|
| 404 | `EVENT_NOT_FOUND` | No encontramos el evento. (also for another club's event and for a withdrawn one) |
| 409 | `EVENT_NOT_PUBLISHED` | El evento no está publicado. |
| 409 | `EVENT_ALREADY_STARTED` | El evento ya empezó: no se puede reprogramar ni retirar. |
| 409 | `EVENT_CHANGED` | El evento cambió mientras lo editabas. Revisá los datos actuales y volvé a intentar. |
| 422 | `NO_CHANGES` | No hay cambios para guardar. |
| 422 | `START_NOT_IN_FUTURE` | La nueva fecha y hora tiene que ser posterior a este momento. |
| 422 | `INVALID_DATETIME` | La fecha y hora no es válida: usá el formato AAAA-MM-DD HH:MM. |
| 422 | `FIELD_NOT_EDITABLE` | Al reprogramar solo se puede cambiar la fecha y la hora. |
| 422 | `CONFIRMATION_REQUIRED` | Confirmá el retiro del evento. |
| 422 (club API) | `EVENT_WITHDRAWN` | El evento fue retirado y no acepta cambios ni asistencias. |

Fixed texts of the screens: "Eventos publicados", "No hay eventos publicados próximos.", "Reprogramar", "Retirar evento", "Cancelar", "Cancelado por el club", "No hay cambios para guardar.", "Este evento fue suspendido.", the confirmation of user story 5 scenario 1, and the schedule effects: "El cronograma no cambia.", "El cierre general pasa al {fecha} a las {hora}.", "Las olas {desde} a {hasta} se suman a la ola {k} y se habilitan el {fecha} a las {hora}. El cierre general pasa al {fecha} a las {hora}.", "Todas las olas quedarían después del nuevo inicio: el cronograma se invalida y hay que generarlo de nuevo."

Audit: `event.rescheduled` (previous and new date and time), `wave_schedule.adjusted` (previous and new effective closing, `merged_into_order`), `wave_schedule.invalidated`, `event.withdrawn`, `wave_segmentation.deleted` and `wave_schedule.deleted` (with the deleted values).

## Notifications

Changes to the catalog of [notifications](../_shared/notifications.md) that this story needs (to apply in the shared document together with the decision):

| Key | Name (UI) | Status | Trigger | Recipients | Opens |
|---|---|---|---|---|---|
| `event_rescheduled` | Evento reprogramado | active | The Admin reprograms a published event (user story 4) | Every Socio of the club with an `activated` account | The event (HU-17) |
| `event_withdrawn` | Evento suspendido | active | The Admin withdraws a published event (user story 5) | Every Socio of the club with an `activated` account | The event; it is not available, the Socio sees "Este evento fue suspendido." |
| `event_restored` | Evento restaurado | **inactive** | None: HU-23B has no restoration | — | — |
| `wave_rescheduled` (new) | Turno de reserva reprogramado | active | A reprogramming merges the Socio's wave into a wave that has not opened | The Socios of the moved waves, with an `activated` account | Their own slot (HU-39) |
| `wave_opened` | Turno de reserva habilitado | active | As today, and also a reprogramming that merges the Socio's wave into a wave already open | The Socios of that wave, or of the moved waves | Their own slot (HU-39) |

| Key | Title | Message | `occurrence_key` |
|---|---|---|---|
| `event_rescheduled` | Evento reprogramado | "{titulo} cambió: ahora es el {fecha} a las {hora}." | `event:{event_id}:rescheduled:{reprogramming_id}` |
| `event_withdrawn` | Evento suspendido | "{titulo}, del {fecha} a las {hora}, se suspendió. Si compraste entradas, comunicate con el club." | `event:{event_id}:withdrawn` (one per event: the withdrawal is final) |
| `wave_rescheduled` | Tu turno de reserva cambió | "Tu turno de reserva para {titulo} cambió: se habilita el {fecha} a las {hora}." | `event:{event_id}:wave-moved:{reprogramming_id}` |
| `wave_opened` | Tu turno de reserva está habilitado | unchanged; `{fecha}` and `{hora}` are the effective closing | `event:{event_id}:wave:{order}:schedule:{schedule_id}`, with the order of the wave the Socio joined |

For `event_withdrawn` the date and time are the start of the event when it was withdrawn; for `wave_rescheduled`, the start of the wave the Socio joined. Order of the catalog: `event_published`, `event_rescheduled`, `event_withdrawn`, `wave_rescheduled`, `wave_opened`, `ranking_completed` (`event_restored` is not shown while it is inactive). The wave opening job reads the effective closing and the merged waves, so it notifies the moved Socios when the wave they joined opens.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 waves of an adjusted schedule open after the start of the match or less than the minimum step before it.
- **SC-002**: 100% of the reprogrammings that touch a schedule end in exactly one of the effects of FR-005, and the start of every unaffected wave is the same before and after.
- **SC-003**: 100% of the Socios of moved waves with an activated account receive exactly one `wave_rescheduled` or one `wave_opened` for the reprogramming.
- **SC-004**: 0 withdrawn events are visible to Socios or in the Admin's lists, count in the scoring or accept attendance; 0 segmentations or schedules remain for them.
- **SC-005**: 100% of reprogrammings and withdrawals appear in the audit log with who, when and the previous and new values.
- **SC-006**: 0 actions of an Admin on an event of another club succeed.

## Assumptions

- The Admin reprograms when the club informs a change by another channel (phone, email); the club stays the source of truth for the rest of the event data.
- The ticket sale is external (HU-37, HU-40 outside the MVP), so "si compraste entradas, comunicate con el club" is the only guidance the system gives about tickets.
- The waves notifications use the existing job and contract of HU-19 (notifications section 4); `notify` is idempotent by Socio and `occurrence_key`.

## Interpretations to confirm (not blocking)

- **"Que se muevan a la última oleada que no estaba afectada"** is read as: the Socios of the affected waves take the start time of the last unaffected wave, and the general closing becomes the new start. A wave that already opened is never affected, and the minimum step counts as overlap.
- **"En dicho caso, además, se les notifique"** is read as: every withdrawal notifies, with or without waves.
- **"Que ni el admin lo pueda ver más"** is read as: the withdrawn event leaves every Admin list, there is no restoration, and the row and its audit are kept.
- **No reason for the withdrawal**: the request asks only for a confirmation, so no reason is stored. If the team wants one for the audit, it is an optional internal field that is never shown to Socios.

## Decisions adopted (2026-11-18, decision 62 of the specs README)

1. **HU-23B replaces HU-23.** Dropped: the review of club changes (HU-23 user story 1, scenarios 1 to 7 and 13), the 24-hour window for the class or points (scenarios 8 and 9), the restoration (user story 2, scenario 7) and the required withdrawal reason. The schedule rules of HU-23 scenarios 10 to 12 become the merge of user story 3.
2. **The type never changes**: a Partido is never turned into an institutional/amateur event, or the other way round.
3. **A reprogramming changes only the date and time.** The class of a Partido and the points of an institutional/amateur event stay fixed once published (HU-22 scenario 9, FR-008, unchanged). "Tipo de partido" in the request is not editable; with no class change there is no class-only notification either.
4. **Catalog changes** (notifications section 2): new type `wave_rescheduled`; `event_withdrawn` is renamed "Evento suspendido" and takes the generic text without the reason, with a single occurrence per event; `event_restored` becomes inactive. This replaces the withdrawal and restoration parts of decision 61.
5. **Consequences in other specs**: the effective closing and `merged_into_order` of `WaveSchedule` are defined here (HU-37 only mentions them in its assumptions, decision 33), the wave opening job reads them (notifications section 4), `withdrawn` is final (cross-cutting section 4), and the club's changes to published events stay omitted (data contract section 5).

## Implementation Status

The code of HU-23 on `merge-hu-19-20con23` covers part of this story and needs these changes:

- `retirar_evento` / `restaurar_evento` (`app/services/evento_service.py`) require a reason and allow restoration; the withdrawal does not delete the segmentation or the schedule, and `segmentation_service` still lists withdrawn events as segmentable.
- The schedule rules of the approval (`aprobar_cambio_evento`) invalidate when no wave opened, or set `closing_at = new_start` otherwise. Since the wave starts are derived from `opening_at` and `closing_at`, that assignment moves the start of **every** wave, which this story forbids; it needs the effective closing of Key Entities.
- There is no direct reprogramming by the Admin: the change comes from the club (`PUT /api/v1/eventos/{id}`, which creates a `pendiente_revision` change) and is approved or rejected. That flow, the restoration and the 24-hour window (`ajustar_clase_o_puntos_reprogramacion`) are removed with this story; the club's `PUT` of a published event goes back to being omitted.
- **User story 1 done**: `GET /admin/events/published` (`app/services/published_events_service.py`) lists the upcoming published events of the Admin's club (`CurrentAdminClub`, `club_id` and `X-Club-ID` ignored) with `version` (new column, migration `8d4f2a6c1e93`) and the schedule summary; tests in `tests/test_hu23b_published_events.py`. The schedule summary gains `merged_into_order` with user story 3.
- **User story 2 done**: `POST /admin/events/{event_id}/reschedule/preview` and `/reschedule` (`published_events_service.preview` / `reschedule`) change only the date and time of a listed event (a date without offset is read in Buenos Aires), keep it `published` with its class or points, add 1 to `version` and clear the cancellation flag. Any other field answers `FIELD_NOT_EDITABLE`, a bad format `INVALID_DATETIME`, the same instant `NO_CHANGES`, a start not in the future `START_NOT_IN_FUTURE`, a stale `expected_version` (or an effect that changed since the preview) `EVENT_CHANGED`; an event of another club, withdrawn or historical `EVENT_NOT_FOUND`, a pending one `EVENT_NOT_PUBLISHED`, a started one `EVENT_ALREADY_STARTED`. Each reprogramming stores an `EventReprogramming` row (table `event_reprogrammings`, migration `863f7cb39c90`), audits `event.rescheduled` and `wave_schedule.adjusted` / `wave_schedule.invalidated`, and generates `event_rescheduled` after the commit with key `event:{event_id}:rescheduled:{reprogramming_id}`. Tests in `tests/test_hu23b_reschedule.py` and `tests/test_hu23b_reschedule_waves.py`.
- **User story 3 done**: `scoring/wave_schedule.reschedule_impact` (pure, tests in `tests/test_hu23b_schedule_adjustment.py`) decides the effect; `WaveSchedule` gains `effective_closing_at` and `merged_into_order` (migration `863f7cb39c90`) and `invalidation_reason` (`waves_regenerated` or `event_rescheduled`, migration `4bb2b886ba54`), all cleared on regeneration. The HU-37 view returns `invalidation_reason`, so the Admin is told why to generate the schedule again, and the front shows merged waves as "Ola k (incluye las olas k+1 a N)". An overlapped draft is invalidated with no wave notification (scenario 7); a second reprogramming works on the current waves, never splits a merge or moves the closing later, and regenerating before the first wave opens discards the adjustments (the front warns about it in the replacement confirmation; scenario 8); `wave_schedule.adjusted` / `wave_schedule.invalidated` carry the previous and new `{status, closing_at, merged_into_order}`, `moved_waves` and `reason: event.rescheduled` (scenario 9); the segmentation never changes (scenario 10). API tests per scenario in `tests/test_hu23b_wave_adjustment.py`. The Admin's schedule view (HU-37, plus `generated_closing_at` and `merged_into_order`), the Socio's slot (HU-39: the start of the joined wave, "Ola k de M") and the wave opening job (moved Socios are notified with the wave they joined, same key) read them.
- **User story 4 done**: after the commit, `published_events_service.notify_rescheduled` generates `event_rescheduled` for the club and, when waves were merged, `generators.waves_moved` notifies the Socios of the moved waves (activated accounts, not dado de baja): `wave_rescheduled` with the start of the wave they joined (key `event:{event_id}:wave-moved:{reprogramming_id}`) if it has not opened, or `wave_opened` right away with the new closing and the job's key if it has, so the job never repeats it. An invalidated schedule or a closing adjustment generates no wave notification; a failure never undoes the reprogramming. The preview and the response count both (`notifications.wave_rescheduled` / `wave_opened`), and the front shows the count in the preview and opens `wave_rescheduled` on the Socio's slot. Tests in `tests/test_hu23b_wave_notifications.py`.
- The withdrawal and restoration endpoints still read the club from the optional `X-Club-ID` header; this story needs `CurrentAdminClub`.
- Notifications: `event_rescheduled`, `event_withdrawn` and `event_restored` are generated from `app/routers/admin_events.py` (decision 61). The catalog (`app/notifications/catalog.py`) has `wave_rescheduled` (user story 4) but still has `event_withdrawn` as "Evento cancelado" with the reason and `event_restored` active.

## Revision Notes

- v1: created from the reprogramming and withdrawal flows given by the team, with the wave merge, the generic suspension notice and the missing scenarios and edge cases (concurrency, minimum step, waves already open, drafts, repeated reprogrammings, club resends of a withdrawn event, tenancy).
- v1.1: team decisions adopted (decision 62): replaces HU-23, the type never changes, a reprogramming changes only the date and time (class and points fixed as in HU-22), catalog changes.
- v1.2 (implementation of user story 2): new error `INVALID_DATETIME` for scenario 6, the optional `expected_schedule_effect` and `expected_merged_into_order` of the reprogramming (scenario 7: confirming applies exactly what the preview showed), and `target_wave_starts_at` and `adjusted` in the responses.
- v1.3 (implementation of user story 3): `invalidation_reason` in the schedule of HU-37, so the Admin knows the schedule was invalidated by a reprogramming (scenario 6).

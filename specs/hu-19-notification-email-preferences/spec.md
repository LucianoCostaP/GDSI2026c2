# Feature Specification: Configure Email Notifications

**Feature Branch**: `hu-19-notification-email-preferences`
**Created**: 2026-11-14 (v1)
**Status**: Draft
**Backlog Reference**: HU-19 (Estimate: 3, Priority: Baja, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [notifications](../_shared/notifications.md), [data contract](../_shared/data-contract.md)
**Input**: "As a Socio of the club, I want to configure which notifications I want to receive by email, so that I receive only the information that interests me."

**Context**: this story covers the **email channel** of the notifications: the Socio's preferences, the generation of the notifications of the catalog and their delivery by email. The in-app inbox is HU-20. The catalog, recipients, texts, destinations and delivery rules are in [notifications](../_shared/notifications.md); this spec does not repeat them.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure Email Preferences (Priority: P1)

As a Socio of the club, I want to turn on or off the email for each type of notification, and all of them at once, so that I receive only what interests me.

**Why this priority**: it is the story's request; without it the Socio cannot control the emails.

**Independent Test**: log in as a Socio, open "Mi Perfil" and the notification settings; verify the defaults, turn one type off, reload and verify it persisted, turn the general switch off and on and verify the per-type values come back.

**Acceptance Scenarios**:

1. **Given** a logged-in Socio, **When** they open "Mi Perfil" (HU-10), **Then** they see the access "Notificaciones por correo", and following it opens the settings screen.
2. **Given** the settings screen, **When** it loads, **Then** it shows a general switch "Recibir notificaciones por correo" and, below it, one switch per **active** type of the catalog, each with its name and a one-line description. Inactive types (for example `event_rescheduled` before HU-23) are not shown.
3. **Given** a Socio who never changed anything (including a newly activated account and a Socio who existed before this feature), **When** they open the screen, **Then** the general switch and every type are on.
4. **Given** the screen, **When** the Socio turns one type off or on, **Then** the change is saved at that moment, with no "Guardar" button, the other switches do not change and the Socio sees "Guardamos tu cambio.".
5. **Given** the Socio saved a change, **When** they reload the screen or log in again, **Then** the switches show the saved values.
6. **Given** the general switch off, **When** the Socio looks at the screen, **Then** they are told "Desactivaste todas las notificaciones por correo. Igual las vas a ver en tu bandeja." and the per-type switches keep their saved values and stay editable.
7. **Given** the general switch turned off and then on again, **When** the screen loads, **Then** every type has the value it had before.
8. **Given** a change that cannot be saved, **When** the request fails, **Then** the switch returns to its previous value and the Socio sees "No pudimos guardar el cambio. Intentá de nuevo.".
9. **Given** a Socio with an email on record, **When** the screen loads, **Then** it shows the address where they will receive the emails, masked (`j***@gmail.com`).
10. **Given** a Socio without an email on record, **When** the screen loads, **Then** they are told "No tenés un email registrado, por eso no vas a recibir notificaciones por correo. Contactá al club." The switches can still be changed and saved.
11. **Given** a type added to the catalog after the Socio saved their preferences, **When** the Socio opens the screen, **Then** the new type is on.
12. **Given** a user without a session, **When** they try to read or change the preferences, **Then** the server rejects the request; **given** an Admin, **then** it is rejected too; **and** a Socio can only read and change their own preferences.

---

### User Story 2 - Receive Notifications by Email According to the Preferences (Priority: P1)

As a Socio of the club, I want the system to email me the notifications I left on, and only those, so that the emails match what I chose.

**Why this priority**: preferences are useless if nothing is sent.

**Independent Test**: with two Socios, one with a type off and one with all on, publish an event (HU-22); verify both get the notification in the inbox and only the second gets the email. Turn the general switch off for the second, publish another event and verify no email.

**Acceptance Scenarios**:

1. **Given** a notification is generated for a Socio, **When** it is stored, **Then** it is in their inbox regardless of their preferences (HU-20).
2. **Given** the notification, **When** its email is dispatched, **Then** it is sent only if the Socio is not dado de baja, has an email, the general switch is on and the switch of that type is on, checked at dispatch time (notifications section 5).
3. **Given** a type turned off, **When** a notification of that type is dispatched, **Then** no email is sent and the notification stays in the inbox.
4. **Given** the general switch off, **When** any notification is dispatched, **Then** no email is sent and the notification stays in the inbox.
5. **Given** the Socio changes a preference, **When** the next email is dispatched, **Then** the new value applies, including emails already queued and not yet sent. Emails already sent are not affected.
6. **Given** an email that cannot be delivered, **When** the send fails, **Then** the notification stays in the inbox, the failure is recorded, nothing is retried and the other recipients are still attempted.
7. **Given** a delivery provider that is down or slow, **When** a ranking completes or an event is published, **Then** that process finishes normally and is not delayed by the emails.
8. **Given** the same occurrence reported twice (a rerun of the job, a double click), **When** the notifications are generated, **Then** each Socio receives one notification and one email.
9. **Given** an email of a notification, **When** the Socio opens it, **Then** it has the title as subject, the message, a button to the destination of notifications section 3 and the line "Podés cambiar qué avisos recibís por correo desde Mi Perfil.".
10. **Given** the access codes, activation codes and Admin invitations (HU-01, 05, 06, 07, 08), **When** they are sent, **Then** they ignore the preferences: they are not notifications.

---

### User Story 3 - Generate the Notifications of the Catalog (Priority: P2)

As a Socio of the club, I want to be notified when something I care about happens, so that I do not have to keep checking the app.

**Why this priority**: it feeds the inbox and the emails; each type is an independent slice.

**Independent Test**: for each active type, cause its trigger and verify who receives it, the exact text and the destination.

**Acceptance Scenarios**:

1. **Given** an event published by the Admin or automatically (HU-22), **When** it becomes `published`, **Then** every Socio of the club with an `activated` account gets `event_published` with the text of notifications section 2. A discarded or still pending event generates nothing.
2. **Given** a `confirmed` schedule, **When** the start time of a wave arrives, **Then** the Socios of that wave get `wave_opened`, and the Socios of other waves get nothing at that moment.
3. **Given** a `draft` or `invalidated` schedule, or a general closing already passed, **When** a wave start arrives, **Then** nothing is generated.
4. **Given** a wave whose start passed more than the catch-up window ago when the job first sees it, **When** the job runs, **Then** it is skipped and logged.
5. **Given** a ranking that finishes `completed` (HU-25), **When** it is stored, **Then** the Socios with an entry in it and an `activated` account get `ranking_completed`. The ranking is `completed` and in force whether or not the notifications or emails succeed.
6. **Given** a ranking that finishes `failed`, **When** it is marked, **Then** no notification is generated.
7. **Given** an institutional/amateur event, **When** it is published, **Then** `event_published` is generated like for a Partido; no `wave_opened` exists for it.
8. **Given** the type `event_rescheduled` before HU-23 exists, **When** the system runs, **Then** it generates nothing and the type is not offered to the Socio.
9. **Given** a Socio without an `activated` account or dado de baja when the notification is generated, **When** it is generated, **Then** they get nothing.

---

### Edge Cases

- **Defaults without storing**: no value means on. Activating an account writes no preferences.
- **Baja and alta**: preferences stay stored. A Socio dado de baja receives no email (reason `inactive`); with a new alta, their saved choices apply again.
- **Two devices**: the last change wins. Saving the value a switch already has is accepted and not audited.
- **Unknown or inactive type**: a request for a type not in the active catalog is rejected (`404 NOTIFICATION_TYPE_NOT_FOUND`, "Ese tipo de notificación no existe.").
- **Email changed by the club (HU-43)**: the next email goes to the new address; the Socio cannot edit it here.
- **Dummy email domains**: behave as the mailer already does (printed, not sent).
- **Wave notification and the closing**: the text of `wave_opened` carries the general closing date; it is frozen at generation.
- **Volume**: `ranking_completed` goes to every Socio in the ranking. Notifications are stored in bulk and the emails queued in batches, so the ranking does not wait for them.
- **Lost notification**: a crash between the commit of the trigger and the generation can lose a notification; accepted in the MVP.
- **Language and accessibility**: UI and emails in Spanish (Argentina); switches are reachable by keyboard, have a text label and state (not color only), and the screen is readable at 200% zoom (cross-cutting section 6).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST show, from "Mi Perfil", the notification settings of the logged-in Socio, with a general switch and one switch per active type.
- **FR-002**: System MUST treat every switch as on when no value was saved, including new accounts and new catalog types.
- **FR-003**: System MUST save each change when it is made and apply it from that moment, including to emails queued and not yet sent.
- **FR-004**: System MUST keep the per-type values when the general switch is turned off, and restore them when it is turned on.
- **FR-005**: System MUST show the Socio's email masked and warn when there is none.
- **FR-006**: System MUST generate the notifications of notifications section 2 for their recipients, one per recipient and occurrence.
- **FR-007**: System MUST store every generated notification in the inbox regardless of preferences.
- **FR-008**: System MUST send the email only if the Socio is not dado de baja, has an email, and the general switch and the type switch are on, checked at dispatch time.
- **FR-009**: System MUST NOT block, delay or undo the triggering process (publication, ranking, schedule) because of the notification or its email.
- **FR-010**: System MUST attempt every recipient, record each failure and not retry.
- **FR-011**: System MUST dispatch emails asynchronously and in batches.
- **FR-012**: System MUST NOT generate `event_rescheduled` until HU-23 calls the contract, and MUST NOT show inactive types.
- **FR-013**: System MUST NOT apply preferences to access codes, activation codes or invitations.
- **FR-014**: System MUST audit every change of a preference with who, when, previous and new value, and skip changes that keep the value.
- **FR-015**: System MUST allow only a Socio with a valid session to read and change their own preferences, enforced on the server; the club comes from the account.

### Key Entities

- **NotificationType** (product catalog): key, name, description, status (`active` / `inactive`), recipients rule, destination. See notifications section 2.
- **NotificationPreference**: Socio account, scope (general, or a type key), `email_enabled`, updated at. No row means on.
- **Notification**: created by HU-20 (fields and table); this story adds `email_status` (`pending` / `sent` / `failed` / `not_sent`), reason when `not_sent` (`inactive`, `no_email`, `master_off`, `type_off`), emailed at and error when `failed`.

## API

Socio only. The club comes from the Socio's account; a `club_id` parameter is ignored (cross-cutting section 9).

| Method and path | Body | Response |
|---|---|---|
| `GET /member/notifications/preferences` | — | `200 NotificationPreferencesOut` |
| `PUT /member/notifications/preferences/email` | `{ "enabled": bool }` | `200 NotificationPreferencesOut` (general switch) |
| `PUT /member/notifications/preferences/types/{type}` | `{ "enabled": bool }` | `200 NotificationPreferencesOut` · `404 NOTIFICATION_TYPE_NOT_FOUND` |

`NotificationPreferencesOut`: `email_enabled` (general), `email_masked` (`null` when the Socio has no email), `types [{ type, name, description, email_enabled }]` for the active types, in catalog order.

| HTTP | Code | Message |
|---|---|---|
| 401 | `NOT_AUTHENTICATED` | (session errors as in HU-05) |
| 403 | `FORBIDDEN` | An Admin cannot use these endpoints |
| 404 | `NOTIFICATION_TYPE_NOT_FOUND` | Ese tipo de notificación no existe. |
| 422 | `INVALID_PREFERENCE` | El valor tiene que ser verdadero o falso. |

Fixed texts of the screen: "Guardamos tu cambio.", "No pudimos guardar el cambio. Intentá de nuevo.", "Desactivaste todas las notificaciones por correo. Igual las vas a ver en tu bandeja.", "No tenés un email registrado, por eso no vas a recibir notificaciones por correo. Contactá al club."

Audit: `notification_preference.changed`, `entity = "notification_preference"`, details `{ scope: "all" | type, previous, new }`, actor = the Socio's account.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of notifications generated for a recipient appear in their inbox, whatever their preferences.
- **SC-002**: 0 emails are sent for a type or a general switch that was off at dispatch time.
- **SC-003**: 100% of Socios without saved preferences receive the emails of every active type.
- **SC-004**: 0 duplicated notifications or emails for the same occurrence and Socio.
- **SC-005**: 0 triggering processes (publication, ranking, schedule) are delayed or undone by a failed or slow email.
- **SC-006**: 100% of preference changes that alter a value leave an audit entry; 0 entries for changes that keep it.

## Assumptions

- The global navigation menu and "Mi Perfil" (HU-10, HU-11) exist; this story adds one link inside "Mi Perfil".
- The Socio's email comes from the roster (HU-43) and is not editable here.
- The mailer and its layout already exist; the new part is the dispatch queue and the notification templates.
- The mail provider is the one the system already uses for access codes and invitations (`app/mailer.py`); no new provider is introduced.

## Implementation Status

**Depends on HU-20**, which is built first and creates the notifications table and the inbox (notifications section 10). Suggested build order inside this story: user story 3 (generators, so the inbox fills with real notifications), then user story 1 (preferences) and user story 2 (email dispatch). Nothing of this story exists yet: no preference model, no email fields, no dispatch queue, no endpoints. Reusable: `app/mailer.py` (`send_email`, layout and logo), `app/audit.py`, the publication flow of `evento_service.publicar_eventos_automaticos` and the manual one (HU-22), the ranking run of HU-25, the schedules of HU-37. Needs: a migration that adds the email fields to the notifications table and creates the preferences table, `FRONTEND_BASE_URL` setting, the dispatch worker and the wave-opening job (the app has no scheduler yet; see `docs/brechas-codigo.md`).

## Revision Notes (v1)

- v1.1: built after HU-20; adds the email fields to the table that HU-20 creates (notifications section 10, decision 60).
- Created with HU-20. Decisions 50 to 60 of the specs README.

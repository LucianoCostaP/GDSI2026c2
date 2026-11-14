# Notifications (shared by HU-19 and HU-20)

Rules for the notifications the system generates for Socios: what exists, who receives each one, how it reaches the in-app inbox (HU-20) and the email channel (HU-19), and where the Socio lands when opening it. Individual specs reference this file instead of repeating it. Values marked **default** are system settings (cross-cutting section 8).

## 1. Principles

1. **Two channels, one notification.** Every notification is stored in the Socio's inbox (HU-20). The email is an optional second channel controlled by the Socio's preferences (HU-19). Preferences never affect the inbox.
2. **Independent from the process that triggers it.** Generating or sending a notification never blocks, delays or undoes the process that caused it. A ranking that completes stays `completed`, a published event stays `published`, a failed email never fails anything. Generation happens after the triggering change is committed.
3. **Additive.** Generators read the state the existing stories already produce. They change nothing in HU-22, HU-25, HU-37 or HU-23 beyond calling the notification contract (section 4).
4. **Best effort, no retries.** The system tries to reach every recipient. A failure is recorded and does not stop the rest. There are no automatic retries in the MVP.
5. **Not every email is a notification.** Access codes, activation codes and Admin invitations (HU-01, 05, 06, 07, 08) are part of authentication: they are never affected by preferences and never appear in the inbox.
6. **Club scope.** Notifications belong to a club. A Socio only receives and sees notifications of their own club (cross-cutting section 9).

## 2. Catalog

The catalog lives in the product, like the formula catalog (decision 35): adding a type is a product release, never a screen. A type is `active` (generated) or `inactive` (defined but not generated yet). Preferences and the inbox only show **active** types.

| Key | Name (UI) | Status | Trigger | Recipients | Opens |
|---|---|---|---|---|---|
| `event_published` | Nuevo evento publicado | active | An event becomes `published`, manually or automatically (HU-22), for both event types | Every Socio of the club with an `activated` account | The event: upcoming events list (HU-17) with that event highlighted |
| `event_rescheduled` | Evento reprogramado | **inactive** until HU-23 is built | A club change of a published event is approved (HU-23) | Every Socio of the club with an `activated` account | The event, as above |
| `wave_opened` | Turno de reserva habilitado | active | The enablement time of a wave of a `confirmed` schedule arrives (HU-37). Partidos only | The Socios of **that wave**, with an `activated` account | Their own slot (HU-39) |
| `ranking_completed` | Ejecución del ranking | active | A ranking becomes `completed` (HU-25) | The Socios with an entry in that ranking and an `activated` account | Mi puntaje (HU-14) |

Notes:

- A Socio **without an `activated` account** at generation time gets nothing, and does not receive past notifications when activating later.
- A Socio **with overdue fees** can log in (decision 6), so receives `event_published`; they are not in the ranking or in any wave, so they do not receive `ranking_completed` or `wave_opened`.
- A Socio **dado de baja** receives nothing (cross-cutting, decision 31). Their notifications and preferences are kept and come back with a new alta.
- `event_rescheduled` is defined here so that the preference screen, the inbox and the mail can be built once. It starts being generated when HU-23 calls the contract of section 4; until then it is inactive and does not appear anywhere.

### Texts

Exact texts, so tests can compare them (decision 24). Dates and times are Buenos Aires time, written `{fecha}` = `dd/mm/aaaa` and `{hora}` = `HH:mm`.

| Key | Title | Message |
|---|---|---|
| `event_published` | Nuevo evento publicado | "Ya podés ver {titulo}, el {fecha} a las {hora}." |
| `event_rescheduled` | Evento reprogramado | "{titulo} cambió: ahora es el {fecha} a las {hora}." |
| `wave_opened` | Tu turno de reserva está habilitado | "Ya podés reservar para {titulo}. Tu acceso está habilitado hasta el {fecha} a las {hora}." |
| `ranking_completed` | Se actualizó el ranking | "Se calculó un nuevo ranking. Consultá tu puntaje y tu posición." |

`{titulo}` is the event title. For `wave_opened` the date is the general closing of the schedule. The text is **frozen when the notification is generated**: later changes to the event or the schedule do not rewrite it.

## 3. Where a notification opens

The notification stores its `type` and a `reference` (`{ event_id }` for the three event types, `{ ranking_id }` for `ranking_completed`), never a URL. The front maps type to screen:

| Type | Screen | If the destination is not available |
|---|---|---|
| `event_published`, `event_rescheduled` | `GET /events/upcoming` list (HU-17) with the referenced event highlighted | The event is not in the list (it started, was discarded, is not `published` or is not of the club): the Socio sees "Este evento ya no está disponible." and the list is shown without highlight |
| `wave_opened` | `GET /member/events/{event_id}/slot` (HU-39) | `404 EVENT_NOT_FOUND`: same message "Este evento ya no está disponible." HU-39 already explains its own states (closed, no turn) |
| `ranking_completed` | `GET /member/scoring/current` (HU-14) | None: HU-14 explains its own states (for example, a Socio no longer in the ranking) |

- Opening a notification from the inbox marks it as read (HU-20).
- The **email** carries the same destination as a button. The link requires a session: with none, the Socio logs in first (HU-05). Returning to the destination after login is a front-end convenience; if it cannot be restored the Socio lands on the home screen. This does not change HU-05.
- The link base is the setting `FRONTEND_BASE_URL` (section 7).

## 4. Generation contract

Every generator calls the same internal operation:

`notify(type, occurrence_key, recipients, reference, params)`

- Creates **one notification per recipient** in state `unread`, with the frozen text of section 2, and queues its email.
- **No duplicates**: the pair (Socio, `occurrence_key`) is unique. Calling again with the same key creates nothing and sends nothing, so retries, double clicks and job reruns are safe.
- **Never raises into the caller.** Errors are logged; the triggering process continues.
- It is called after the triggering change is committed. A crash between the commit and the call can lose that notification; this is accepted in the MVP (the Socio still sees the change in the app).

| Type | `occurrence_key` | Generator |
|---|---|---|
| `event_published` | `event:{event_id}:published` | End of the publication flow of HU-22, manual and automatic |
| `event_rescheduled` | `event:{event_id}:rescheduled:{change_id}` | Approval of a change in HU-23 |
| `wave_opened` | `event:{event_id}:wave:{order}:schedule:{schedule_id}` | Periodic job, below |
| `ranking_completed` | `ranking:{ranking_id}` | Completion of the run in HU-25; a `failed` ranking generates nothing |

**Wave opening job.** It runs at least every minute, like the publication job of HU-22, and is idempotent. It reads `confirmed` schedules (read-only: HU-37 does not change) and, for each wave whose start has arrived and whose general closing has not passed, calls `notify` for the Socios of that wave. A schedule that is `draft` or `invalidated` generates nothing. A wave whose start is **more than `wave_notification_catchup_minutes` in the past** when the job first sees it (default 60) is skipped and logged, so an outage or the first run after deployment does not flood Socios with old openings.

## 5. Email delivery

Delivery runs **asynchronously and in batches** (`notification_dispatch_batch_size`, default 500), never inside the request or the process that triggered it. A ranking notifies every Socio in it; the calculation does not wait for the emails.

For each queued email, **at dispatch time** the system checks, in this order, and sends only if all pass:

| Check | If it fails: `email_status = not_sent`, reason |
|---|---|
| The Socio is not dado de baja | `inactive` |
| The Socio has an email on record | `no_email` |
| The general email switch is on (HU-19) | `master_off` |
| The email switch of that type is on (HU-19) | `type_off` |

- A change of preferences applies **from that moment**: it is read when each email is dispatched, so it also affects emails still queued, and never emails already sent.
- A rejected or failed send ends `failed` with the error recorded. The notification stays in the inbox. No retry.
- States of `email_status`: `pending` → `sent`, `failed` or `not_sent`.
- The inbox never depends on `email_status`.
- **Content**: subject = title of section 2 (the mailer's layout and logo apply), body = the message, the destination as a button (the mailer turns a paragraph that is only a link into a button), and a closing line with the link to the notification settings (HU-19): "Podés cambiar qué avisos recibís por correo desde Mi Perfil." A one-click unsubscribe with a token is outside the MVP.
- Emails to test domains follow the mailer's current behavior (`is_dummy_email`).

## 6. Preferences model

- Two levels, both controlled by the Socio: a **general switch** and **one switch per active type**.
- An email is sent only if the general switch **and** the type switch are on (section 5).
- **Default: everything on.** No stored value means on. This covers new accounts, Socios that existed before the feature, and any type added to the catalog later. Nothing is written when the account is activated.
- Turning the general switch off keeps the per-type values. Turning it on again restores them.
- Preferences are kept through a baja and restored with a new alta.

## 7. Settings (defaults)

| Setting | Default | Used by |
|---|---|---|
| Notifications per page in the inbox | 20 (maximum 100) | HU-20 |
| Email dispatch batch size (`notification_dispatch_batch_size`) | 500 | HU-19 |
| Catch-up window for wave openings (`wave_notification_catchup_minutes`) | 60 | HU-19 |
| Base URL of the front for email links (`FRONTEND_BASE_URL`) | none (must be configured; without it emails carry no button and the failure is logged) | HU-19 |
| Retention of notifications | kept, no expiry in the MVP | HU-20 |

## 8. Audit and privacy

- **Audited**: every change of a preference (who, when, previous and new value): `notification_preference.changed`, `entity = "notification_preference"`. A change that sets the value it already had is not recorded.
- **Not audited**: generation of notifications, emails sent or failed (they are logged, with no more personal data than the recipient's account id), and marking as read.
- Responses never include the email address unmasked: it is shown as `j***@gmail.com` (cross-cutting section 3).

## 9. Out of the MVP

Push notifications, real-time updates of the inbox, deleting or archiving notifications, marking as unread, filters, automatic retries, one-click unsubscribe, an Admin view of delivery results, notifications for the Admin, and email for other events (for example, a change of fee status).

## 10. Build order and ownership of the data

HU-20 is built **before** HU-19, so the inbox can be shown while the generators do not exist yet.

1. **HU-20 first.** It creates the table of notifications with the fields the inbox needs (id, club, Socio account, `type`, `reference`, title, message, created at, state, read at, `occurrence_key`; unique per Socio and `occurrence_key`) and its endpoints. It is tested and shown with **seeded notifications**: one of each active type, some read and some unread, for the demo Socios.
2. **HU-19 generators (user story 3).** They fill the inbox from the real triggers, using the contract of section 4. From here the inbox is no longer seeded.
3. **HU-19 preferences and email (user stories 1 and 2).** They add the email fields to the table (`email_status`, reason, emailed at, error) in their own migration, create the preferences, and dispatch the emails.

The inbox never reads the email fields, so HU-20 does not change when HU-19 adds them. The scenario "the inbox shows a notification even when the email is off or failed" (HU-20 scenario 5) can only be fully verified once HU-19 delivers user stories 2 and 3.

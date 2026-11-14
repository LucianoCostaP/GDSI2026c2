# Feature Specification: Notification Inbox

**Feature Branch**: `hu-20-notification-inbox`
**Created**: 2026-11-14 (v1)
**Status**: Draft
**Backlog Reference**: HU-20 (Estimate: 2, Priority: Baja, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [notifications](../_shared/notifications.md)
**Input**: "As a Socio of the club, I want to see a list of my notifications inside the system, so that I can check the notices I received, even if I turned off the email."

**Context**: the notifications are generated, and optionally emailed, by HU-19 (catalog, recipients, texts and destinations in [notifications](../_shared/notifications.md)). This story is the inbox where the Socio reads them. It never depends on the email preferences or on whether an email was sent.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - List My Notifications (Priority: P1)

As a Socio of the club, I want to see all the notifications I received, newest first, so that I can check them whenever I want.

**Why this priority**: it is the story's request.

**Independent Test**: generate notifications of two types for a Socio (HU-19), with the email turned off, and verify the list, its order, the content of each item, the read/unread distinction and the empty state.

**Acceptance Scenarios**:

1. **Given** a logged-in Socio, **When** they open "Notificaciones" from the global navigation menu, **Then** they see every notification they received, ordered chronologically with the most recent first (ties by the most recently created).
2. **Given** the list, **When** it renders, **Then** each item shows its title, its message (what it is about) and the date and time it was generated, in Buenos Aires time, as `dd/mm/aaaa HH:mm`.
3. **Given** read and unread notifications, **When** the list renders, **Then** they are distinguishable: an unread one is shown in bold with the label "Nueva" and a marker, and a read one is shown in normal weight without them. The difference does not rely on color alone.
4. **Given** a Socio with no notifications, **When** they open the inbox, **Then** they see "No tenés notificaciones." instead of an empty screen.
5. **Given** a Socio who turned off the general email switch or a type (HU-19), or whose email failed, **When** they open the inbox, **Then** those notifications are in the list anyway.
6. **Given** more notifications than one page, **When** the Socio reaches the end of the page, **Then** they can load the next one and the global order is kept.
7. **Given** the inbox cannot be loaded (server or network error), **When** the screen renders, **Then** the Socio sees "No pudimos cargar tus notificaciones. Intentá de nuevo." with a retry action, and not the empty-state message.
8. **Given** a user without a session, **When** they request the inbox, **Then** the server rejects the request; **given** an Admin, **then** it is rejected too; **and** a Socio never sees notifications of another Socio or another club.

---

### User Story 2 - Open and Mark as Read (Priority: P1)

As a Socio of the club, I want to open a notification to go to what it talks about and have it marked as read, so that I can tell what I still have to check.

**Why this priority**: without a way to change the state, the read/unread distinction has no use.

**Independent Test**: with three unread notifications, open one and verify it goes to its destination and turns read, mark all as read and verify the counter, and open one whose destination no longer exists.

**Acceptance Scenarios**:

1. **Given** an unread notification, **When** the Socio taps it, **Then** it is marked as read and the Socio goes to its destination: the event for `event_published` and `event_rescheduled`, their own slot for `wave_opened`, "Mi puntaje" for `ranking_completed` (notifications section 3).
2. **Given** a notification whose event is no longer available, **When** the Socio taps it, **Then** it is marked as read, they see "Este evento ya no está disponible." and the inbox stays accessible.
3. **Given** an already read notification, **When** the Socio taps it again, **Then** it goes to the destination and nothing else changes (the first read time is kept).
4. **Given** unread notifications, **When** the Socio chooses "Marcar todas como leídas", **Then** all of their notifications become read and the counter goes to zero.
5. **Given** the global navigation menu, **When** the Socio has unread notifications, **Then** the "Notificaciones" entry shows how many there are (`99+` above 99), and shows no number when there are none.
6. **Given** the Socio marked notifications as read, **When** the menu or the list is shown again, **Then** the counter and the items reflect it.
7. **Given** a notification that is not theirs or does not exist, **When** the Socio tries to mark it as read, **Then** the server answers as for an unknown notification and changes nothing.

---

### Edge Cases

- **Own notifications only**: the inbox shows the notifications of the account of the session; there is no way to request another's (as in HU-10). The club comes from the account.
- **Frozen text**: a notification shows the text it had when it was generated, even if the event or the schedule changed afterwards.
- **No past notifications for new accounts**: notifications are generated only for `activated` accounts (notifications section 2); a Socio who activates later starts with an empty inbox.
- **Overdue fees**: a Socio with overdue fees can log in and sees their inbox.
- **Baja**: a Socio dado de baja cannot log in (decision 31); their notifications are kept and come back with a new alta.
- **No realtime**: a notification generated while the screen is open appears the next time the list or the counter is loaded.
- **Two devices**: marking as read is idempotent; the last state is shown on the next load.
- **Retention**: notifications are kept without expiry in the MVP. Deleting, archiving, marking as unread and filters are outside the MVP.
- **Read-only**: the only actions are opening an item and "Marcar todas como leídas".
- **Accessibility**: the list is reachable by keyboard, the unread state is available to screen readers as text, and the screen is readable at 200% zoom (cross-cutting section 6).
- **Performance**: list and counter answer in under 2 seconds (95th percentile); the counter is requested on every screen, so it must be cheap.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list all the notifications of the logged-in Socio, most recent first, paginated.
- **FR-002**: System MUST show for each one its title, its message and the date and time it was generated, in Buenos Aires time.
- **FR-003**: System MUST distinguish read from unread notifications without relying on color alone.
- **FR-004**: System MUST show "No tenés notificaciones." when there are none, and a different error message when the list cannot be loaded.
- **FR-005**: System MUST list notifications independently of the email preferences and of the delivery result of the email.
- **FR-006**: System MUST mark a notification as read when the Socio opens it and take them to its destination, with the unavailable-destination message when applicable.
- **FR-007**: System MUST offer "Marcar todas como leídas".
- **FR-008**: System MUST show the number of unread notifications in the global navigation menu.
- **FR-009**: System MUST make marking as read idempotent and keep the first read time.
- **FR-010**: System MUST allow only a Socio with a valid session to read and mark their own notifications, enforced on the server; the club comes from the account.

### Key Entities

- **Notification**: id, club, Socio account, `type`, `reference` (`event_id` or `ranking_id`), title, message (frozen text), created at, state (`unread` / `read`), read at and `occurrence_key`. **This story creates the table.** The email delivery fields are added later by HU-19 and the inbox never reads them.

## API

Socio only. The club comes from the Socio's account; a `club_id` parameter is ignored (cross-cutting section 9). Pagination follows the rest of the API (`limit`, `offset`).

| Method and path | Response |
|---|---|
| `GET /member/notifications?limit=20&offset=0` | `200 NotificationListOut` |
| `GET /member/notifications/unread-count` | `200 { "unread_count": int }` |
| `POST /member/notifications/{id}/read` | `200 NotificationOut` · `404 NOTIFICATION_NOT_FOUND` |
| `POST /member/notifications/read-all` | `200 { "marked": int, "unread_count": 0 }` |

`NotificationOut`: `id`, `type`, `title`, `message`, `created_at` (UTC), `state` (`unread` / `read`), `read_at` (UTC or `null`), `reference` (`{ event_id }`, `{ ranking_id }`).
`NotificationListOut`: `items [NotificationOut]`, `total`, `unread_count`, `limit`, `offset`. `limit` is 20 by default and 100 at most.

The email delivery state is not exposed to the Socio.

| HTTP | Code | Message |
|---|---|---|
| 401 | `NOT_AUTHENTICATED` | (session errors as in HU-05) |
| 403 | `FORBIDDEN` | An Admin cannot use these endpoints |
| 404 | `NOTIFICATION_NOT_FOUND` | No encontramos esa notificación. (same answer for another Socio's notification and for a missing one) |

Fixed texts of the screen: "No tenés notificaciones.", "No pudimos cargar tus notificaciones. Intentá de nuevo.", "Este evento ya no está disponible.", "Marcar todas como leídas", "Nueva".

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the notifications generated for a Socio appear in their inbox, in descending chronological order.
- **SC-002**: 0 notifications of another Socio or another club are returned.
- **SC-003**: 100% of the items show the title, the message and the generation date; 100% of the unread ones carry the text label, not only a color.
- **SC-004**: The counter always equals the number of `unread` notifications of the Socio.
- **SC-005**: A Socio with no notifications always sees "No tenés notificaciones.", never a blank screen.

## Assumptions

- The global navigation menu (cross-cutting section 7) can host a counter next to "Notificaciones".
- The notifications are created by HU-19; this story only reads them and changes their read state. It is built first (notifications section 10): until the generators of HU-19 exist, the inbox runs on seeded notifications.
- Scenario 5 of user story 1 (notifications listed whatever the email result) is fully verifiable only when HU-19 delivers the emails; before that it is covered with seeded notifications.
- Notifications are not deleted in the MVP; the volume per Socio stays small (a few per event), so a plain index on (Socio, created at) and (Socio, state) is enough.

## Implementation Status

Nothing exists yet: no model, router or screen. Needs, in this order:

1. The table of notifications with its migration (fields of Key Entities; unique on Socio and `occurrence_key`; indexes on (Socio, created at) and (Socio, state)).
2. A router `/member/notifications` following the pattern of `app/routers/member_scoring.py` (Socio role from `CurrentMember`, club from the account).
3. A seed of demo notifications (one per active type, read and unread) for the demo Socios, added to the seeds of `app/seed.py` so the inbox can be shown before HU-19.
4. The entry and the counter in the global menu, and the screen.

## Revision Notes (v1)

- v1.1: built before HU-19 and owner of the notifications table; seed of demo notifications (notifications section 10, decision 60).
- Created with HU-19. The "mark as read" and the counter are added to the backlog criteria so that the read/unread distinction can change (decisions 50 to 60 of the specs README).

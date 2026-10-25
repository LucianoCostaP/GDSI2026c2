# Feature Specification: Event Reprogramming, Withdrawal and Restoration

**Feature Branch**: `hu-23-event-reprogramming`
**Created**: 2026-10-13 | **Revised**: 2026-10-25 (v3)
**Status**: Draft
**Backlog Reference**: HU-23 (Estimate: 5, Priority: Media, MVP: No)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md)
**Input**: "As an Admin, I want to update an event from the club or withdraw/restore a published event that will not take place, so that I keep the information correct and prevent cancelled events from affecting the Socios or the scoring."

**Context**: the club organizes the events and **sends** their changes to the system (HU-21); the system never calls the club. In the MVP, a change the club sends for a pending event is applied directly (HU-21) and a change for a published event is omitted. This story lets the Admin review and apply the changes the club sends for published events, and withdraw or restore a published event. Notifications by email (HU-19/20) are not included.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Review an Update Sent by the Club (Priority: P1)

As an Admin, I want to review the changes the club sends for an event that was already published, so that the information Socios see stays correct.

**Independent Test**: Publish an event, send a new date for it with the club token, and verify that it waits for review, that the Admin sees the before/after comparison, that after the approval Socios see the new date in HU-17 right away, and that the change is audited.

**Acceptance Scenarios**:

1. **Given** a `published` event whose start has not passed, **When** the club sends an update of it (same `id_externo`) with a different date, time or venue, **Then** the change is stored as `pending review`, nothing changes yet, and the Admin sees a comparison of the registered values and the club's values for date, time and venue.
2. **Given** a change `pending review`, **When** the Admin approves it, **Then** the event is updated, keeps its `published` state with no new publication, and what Socios see (HU-17, HU-39) reflects the change immediately.
3. **Given** a change `pending review`, **When** the Admin rejects it, **Then** the change ends `rejected` and the event stays as it was.
4. **Given** an update with the same values the event already has, **When** it is received, **Then** no change is stored and the club is told the event is up to date.
5. **Given** an update that reports a different type (Partido versus institutional/amateur), **When** it is received, **Then** it is rejected with the reason, because the type decides how the event is scored; the event stays as it was.
6. **Given** an update of an event that already started, or that is `historical`, `discarded` or `withdrawn`, **When** it is received, **Then** it is rejected with the reason.
7. **Given** a new update arrives while another change of the same event is `pending review`, **When** it is stored, **Then** it replaces the pending one, which ends `replaced`.
8. **Given** an approved change of the date, time or venue of a published event, **When** it is applied, **Then** the Admin has 24 hours to adjust the class (Partido) or the points (institutional/amateur event) again; if they do nothing the current class or points are kept.
9. **Given** a published event outside that 24-hour window, **When** the Admin looks for a way to change its class or points, **Then** there is none.
10. **Given** an event with a confirmed wave schedule whose new start is **not before** the schedule's general closing, **When** the change is applied, **Then** the schedule is left as it is.
11. **Given** an event with a confirmed wave schedule whose new start is **before** the general closing and no wave has opened yet, **When** the change is applied, **Then** the schedule is marked `invalidated`, Socios see that the schedule is not defined (HU-39), and the Admin is told to regenerate it (HU-36, HU-37).
12. **Given** the same situation but a wave has already opened, **When** the change is applied, **Then** the general closing is set to the new start, nothing else in the schedule changes, and the Admin is warned about the consequences.
13. **Given** a change was approved or rejected, **When** it is stored, **Then** the audit log records who, when, and the previous and new values of each field.

---

### User Story 2 - Withdraw and Restore an Event (Priority: P1)

As an Admin, I want to withdraw a published event that will not take place, and restore it if needed, so that Socios stop seeing it and it does not affect the scoring.

**Independent Test**: Send the cancellation of a published event with the club token, verify the flag and the offered withdrawal; withdraw it with a reason, verify it disappears from the Socio list, that its segmentation and schedule are voided, that it cannot receive attendance, and that the withdrawal is audited; then restore it and verify it reappears.

**Acceptance Scenarios**:

1. **Given** a `published` event, **When** the club sends its cancellation, **Then** nothing changes for Socios yet, the event is flagged "cancelado por el club" in the admin view, and the action "Retirar evento" is offered.
2. **Given** a `published` event whose start has not passed, flagged or not, **When** the Admin chooses "Retirar evento", **Then** the system asks for a reason (required) and a confirmation that explains the effects.
3. **Given** the Admin confirms, **When** the withdrawal is applied, **Then** the event passes to `withdrawn` and disappears from what Socios see (HU-17, and therefore the simulator of HU-18).
4. **Given** a withdrawn event with a segmentation or a schedule, **When** the withdrawal is applied, **Then** both are voided and no wave opens.
5. **Given** a withdrawn event, **When** the scoring runs, **Then** the event does not count: it takes no part in the frequency denominator and cannot receive attendance (HU-24).
6. **Given** a Socio who opens the screen of a withdrawn event (HU-39) by an old link, **When** it loads, **Then** they are told that the event was withdrawn.
7. **Given** a withdrawn event whose start has not passed, **When** the Admin chooses "Restaurar evento" and confirms, **Then** it returns to `published` and becomes visible again; its wave schedule stays voided until a new one is generated.
8. **Given** an event in `pending importance definition` cancelled by the club, **When** the Admin wants to remove it, **Then** the action is the discard of HU-21, not this withdrawal.
9. **Given** a withdrawal or a restoration, **When** it is stored, **Then** the audit log records who, when, the reason and the state change.

---

### Edge Cases

- **Authorization**: these actions are available only to Admins; Socios cannot reach them, and the server rejects their requests.
- **Eligible events for updates**: `published` events whose start has not passed. Updates of pending events are applied directly by HU-21.
- **Eligible events for withdrawal**: `published` events whose start has not passed. The Admin can withdraw an event the club has not cancelled, for instance when the club announces a cancellation before sending it.
- **Concurrency**: two Admins acting on the same event at once; the second confirmation fails if the event changed in between and the screen is shown again.
- **Publication lead**: the 48-hour lead applies to the initial publication, not to a reprogramming. The club can move a published match closer than 48 hours.
- **No notifications**: Socios are not warned by email (HU-19/20 are outside the MVP); they see the change or the disappearance when they open the app.
- **Attendance and scoring**: an event is updatable or withdrawable only before it takes place, so no attendance exists yet and the scores do not change.
- **Venue**: the venue is informative. A Partido is assumed at the club stadium; the distance model does not change.
- **Postponement**: if the club keeps the same event with a new date, the right action is the update, not the withdrawal.
- **Effects on MVP stories**: the effects of a withdrawal or a reprogramming on HU-17, HU-36, HU-37 and HU-39 (hidden event, voided segmentation and schedule, "evento retirado" and "cronograma no definido" messages) are specified only here, together with the state `withdrawn`. They are built with this story, not with the MVP.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST store the club's updates of a published event whose start has not passed as `pending review`, without applying them.
- **FR-002**: System MUST show the Admin a before/after comparison of date, time and venue and let them approve or reject it.
- **FR-003**: System MUST keep the `published` state on approval and reflect the change to Socios immediately, without a new publication.
- **FR-004**: System MUST reject updates that change the type, or that refer to started, historical, discarded or withdrawn events.
- **FR-005**: System MUST give the Admin 24 hours after an applied change to adjust the class or points, and keep the current ones otherwise.
- **FR-006**: System MUST leave a confirmed wave schedule untouched when the new start is not before its general closing; invalidate it when the new start is before the closing and no wave opened; and move the closing to the new start when a wave already opened.
- **FR-007**: System MUST flag a published event cancelled by the club and offer the withdrawal.
- **FR-008**: System MUST let an Admin withdraw a published event whose start has not passed, with a required reason and a confirmation, moving it to `withdrawn`.
- **FR-009**: System MUST hide a withdrawn event from Socios, void its segmentation and schedule, and keep it out of the scoring and of the attendance load.
- **FR-010**: System MUST let an Admin restore a withdrawn event whose start has not passed, leaving its schedule voided.
- **FR-011**: System MUST audit every reviewed change, withdrawal and restoration (who, when, reason or previous and new values).
- **FR-012**: System MUST restrict these actions to Admins, enforced on the server, and prevent concurrent overwrites.

### Key Entities

- **Event**: as in HU-21, plus the end of the class-or-points adjustment window and the state `withdrawn`.
- **EventChange**: event, values sent by the club, received at, state (`pending review` / `approved` / `rejected` / `replaced`), reviewed by, reviewed at, previous values.
- **EventWithdrawal**: event, withdrawn at, withdrawn by, reason, restored at, restored by.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 changes to published events are applied without the Admin's approval.
- **SC-002**: 100% of approved changes appear in HU-17 immediately and in the audit log with previous and new values.
- **SC-003**: 0 class or points changes are accepted outside the 24-hour window after an applied change.
- **SC-004**: 100% of schedule conflicts end in exactly one of the three outcomes of FR-006.
- **SC-005**: 0 withdrawn events are visible to Socios, count in the scoring or accept attendance.

## Assumptions

- The club sends updates and cancellations with the same `id_externo` it used in HU-21 (data contract, section 5).
- The Admin cannot edit the club's fields by hand: the club is the source of truth.
- The email notifications depend on HU-19/20, which are outside the MVP.

## Implementation Status (prototype `API-Eventos-Pasion-de-10`)

Not implemented: the prototype removed its `PUT` endpoint because this story is outside the MVP. Its schema already has the table `eventos_cambios_pendientes` (state `pendiente_revision`) for changes of visible events, which matches the review of User Story 1.

## Revision Notes

- v1: refresh from the club API with the 24-hour window and the schedule rules.
- v2: added the withdrawal and the restoration, the flag for events the club no longer lists, and the state `withdrawn`.
- v3: aligned with the backlog (outside the MVP, priority Media). The club sends the updates and cancellations (push); an update of a published event waits for the Admin's approval instead of being fetched on demand.

# Feature Specification: Event Reprogramming and Withdrawal (refresh from the Club API) — MVP minimal version

**Feature Branch**: `hu-23-event-reprogramming`
**Created**: 2026-10-13 | **Revised**: 2026-10-13 (v2, adds withdrawal)
**Status**: Draft
**Backlog Reference**: HU-23 (backlog: Estimate 5, Priority Media, MVP: Quizás). **Proposal: bring this minimal version into the MVP with priority Alta.** Estimate to be reviewed: it reuses the club API client of HU-21, and the withdrawal is an extension of the original backlog story.
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md)
**Input**: "As a System Administrator, I want to update the date, time or venue of an event, even if it was already published, and to withdraw an event that will not take place, so that I reflect changes in the schedule and keep the information correct for Socios."

**Why a minimal version**: the club organizes the events and the system takes their data from the club API (HU-21), so the date, time and venue are no longer typed in by the Administrador. Reprogramming means **refreshing the event from the club**, and cancelling means **withdrawing it**. Clubs reschedule and cancel matches often; without this story a published event would keep an outdated or cancelled entry for the whole MVP. Notifications by email (HU-19/20) are not included.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Refresh an Event from the Club (Priority: P1)

As a System Administrator, I want to refresh an event from the club's data, including an already published one, so that the information Socios see is always correct.

**Independent Test**: Publish an event, change its date in the test club API, refresh it as an Administrador, and verify the before/after comparison, that Socios see the new date in HU-17 right away, and that the change is audited.

**Acceptance Scenarios**:

1. **Given** an event in `pending importance definition` or `published` whose start has not passed, **When** the Administrador asks to refresh it, **Then** the system requests the event from the club API by its club reference and shows a comparison of the current values and the club's values for date, time and venue.
2. **Given** the comparison shows changes, **When** the Administrador confirms, **Then** the changes are applied, a published event keeps its `published` state and no new publication is needed, and what Socios see (HU-17, HU-39) reflects the change immediately.
3. **Given** the comparison shows no changes, **When** it is displayed, **Then** the Administrador is told that the event is up to date and nothing is changed.
4. **Given** the club reports a different type for the event (Partido versus institutional/amateur), **When** the comparison is displayed, **Then** the refresh is refused with an explanation, because the type decides how the event is scored; the event stays as it was.
5. **Given** the club no longer lists a published event (for example because it was cancelled), **When** the Administrador asks to refresh it, **Then** nothing is changed, the event is flagged "ya no figura en el club" in the admin view, and the action "Retirar evento" is offered.
6. **Given** the club API is unavailable, times out, is not authorized or answers with an unexpected structure, **When** a refresh is requested, **Then** an error is shown and nothing is changed.
7. **Given** a refresh that changed the date, time or venue of a published event, **When** it is applied, **Then** the Administrador has 24 hours to adjust the class (Partido) or the points (institutional/amateur event) again, and if they do nothing the current class or points are kept.
8. **Given** a published event outside that 24-hour window, **When** the Administrador looks for a way to change its class or points, **Then** there is none.
9. **Given** an event with a confirmed wave schedule whose new start is **not before** the schedule's general closing, **When** the change is applied, **Then** the schedule is left as it is.
10. **Given** an event with a confirmed wave schedule whose new start is **before** the general closing and no wave has opened yet, **When** the change is applied, **Then** the schedule is marked `invalidated`, Socios see that the schedule is not defined (HU-39), and the Administrador is told to regenerate it (HU-36, HU-37).
11. **Given** the same situation but a wave has already opened, **When** the change is applied, **Then** the general closing is set to the new start, nothing else in the schedule changes, and the Administrador is warned.
12. **Given** the change was applied, **When** it is stored, **Then** the audit log records who, when, and the previous and new values of each field.
13. **Given** a logged-in Dirigente or Socio, **When** they look for this action, **Then** it is not available and the server rejects the request.

---

### User Story 2 - Withdraw an Event That Will Not Take Place (Priority: P1)

As a System Administrator, I want to withdraw a published event that will not take place, so that Socios stop seeing it and it does not affect the scoring.

**Independent Test**: Withdraw a published event with a reason, verify it disappears from the Socio list, that its segmentation and schedule are voided, that it cannot receive attendance, and that the withdrawal is audited; then restore it and verify it reappears.

**Acceptance Scenarios**:

1. **Given** a `published` event whose start has not passed, **When** the Administrador chooses "Retirar evento", **Then** the system asks for a reason (required) and a confirmation that explains the effects.
2. **Given** the Administrador confirms, **When** the withdrawal is applied, **Then** the event passes to state `withdrawn` and disappears from what Socios see (HU-17, and therefore the simulator of HU-18).
3. **Given** a withdrawn event with a segmentation or a schedule, **When** the withdrawal is applied, **Then** both are marked void and no wave opens.
4. **Given** a withdrawn event, **When** the scoring runs, **Then** the event does not count: it takes no part in the frequency denominator and cannot receive attendance (HU-24 only accepts published or historical events whose start has passed).
5. **Given** a Socio who opens the screen of a withdrawn event (HU-39) by an old link, **When** it loads, **Then** they are told that the event was withdrawn.
6. **Given** a withdrawn event whose start has not passed, **When** the Administrador chooses "Restaurar evento" and confirms, **Then** it returns to `published`, becomes visible again and any wave schedule stays void until a new one is generated.
7. **Given** an event in `pending importance definition` that the club no longer lists, **When** the Administrador wants to remove it, **Then** the action is the discard of HU-21, not this withdrawal.
8. **Given** a withdrawal or a restoration, **When** it is stored, **Then** the audit log records who, when, the reason and the state change.
9. **Given** a logged-in Dirigente or Socio, **When** they look for these actions, **Then** they are not available and the server rejects the request.

---

### Edge Cases

- **Eligible events for refresh**: `pending importance definition` or `published` events whose start has not yet passed. Historical, discarded, withdrawn and already started events cannot be refreshed.
- **Eligible events for withdrawal**: `published` events whose start has not passed. The Administrador can withdraw even when the club API still lists the event, for instance when the club announces a cancellation before updating its data.
- **Concurrency**: two Administradores acting on the same event at once; the second confirmation fails if the event changed in between and the screen is shown again.
- **Publication lead**: the 48-hour lead applies to the publication, not to a reprogramming. The club can move a published match closer than 48 hours.
- **Pending events**: refreshing does not restart their publication window (HU-21).
- **No notifications**: Socios are not warned by email (HU-19/20 are outside the MVP); they see the change or the disappearance when they open the app.
- **Attendance and scoring**: an event is refreshable or withdrawable only before it takes place, so no attendance exists yet and the scores do not change.
- **Venue**: the venue is informative. A Partido is assumed at the club stadium; if the club moves it elsewhere, the Administrador keeps the event as is (the distance model is unchanged).
- **Postponement**: if the club keeps the same event with a new date, the right action is the refresh, not the withdrawal.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let an Administrador refresh a pending or published event whose start has not passed, from the club API by the club event reference.
- **FR-002**: System MUST show a before/after comparison of date, time and venue and require confirmation to apply it.
- **FR-003**: System MUST keep the `published` state and reflect the change to Socios immediately, without a new publication.
- **FR-004**: System MUST refuse the refresh when the club reports a different event type, and change nothing when the event is not found or the API fails.
- **FR-005**: System MUST give the Administrador 24 hours after an applied change to adjust the class or points, and keep the current ones otherwise.
- **FR-006**: System MUST leave a confirmed wave schedule untouched when the new start is not before its general closing; invalidate it when the new start is before the closing and no wave opened; and move the closing to the new start when a wave already opened.
- **FR-007**: System MUST flag a published event that the club no longer lists and offer the withdrawal.
- **FR-008**: System MUST let an Administrador withdraw a published event whose start has not passed, with a required reason and a confirmation, moving it to `withdrawn`.
- **FR-009**: System MUST hide a withdrawn event from Socios, void its segmentation and schedule, and keep it out of the scoring and of the attendance load.
- **FR-010**: System MUST let an Administrador restore a withdrawn event whose start has not passed, leaving its schedule void.
- **FR-011**: System MUST audit every refresh, withdrawal and restoration (who, when, reason or previous and new values).
- **FR-012**: System MUST restrict these actions to Administradores, enforced on the server, and prevent concurrent overwrites.

### Key Entities

- **Event**: as in HU-21, plus last refreshed at, the end of the class-or-points adjustment window and the state `withdrawn`.
- **EventChange**: event, changed at, changed by, previous values, new values.
- **EventWithdrawal**: event, withdrawn at, withdrawn by, reason, restored at, restored by.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of applied changes appear in HU-17 immediately and in the audit log with previous and new values.
- **SC-002**: 0 refreshes persist anything when the API fails or the type differs.
- **SC-003**: 0 class or points changes are accepted outside the 24-hour window after a refresh.
- **SC-004**: 100% of schedule conflicts end in exactly one of the three outcomes of FR-006.
- **SC-005**: 0 withdrawn events are visible to Socios, count in the scoring or accept attendance.
- **SC-006**: 100% of withdrawals and restorations carry a reason or a record in the audit log.

## Assumptions

- The club API returns the current values of an event by its reference (the same one HU-21 stored). A cancelled event is one the club no longer lists.
- The refresh is manual: the Administrador decides when to ask. Automatic synchronization of published events is outside this version.
- The full original HU-23 lets the Administrador edit the fields by hand. This version does not: the club is the source of truth.
- The withdrawal is not in the original backlog; it was added because a cancelled published event would otherwise stay visible.
- The email notifications of the original HU-23 and HU-22 depend on HU-19/20 and stay out of the MVP.

## Revision Notes

- v1: refresh from the club with the 24-hour window and the schedule rules.
- v2: added the withdrawal and the restoration of an event that will not take place, the flag for events the club no longer lists, and the state `withdrawn`.

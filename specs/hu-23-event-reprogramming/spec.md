# Feature Specification: Event Reprogramming and Withdrawal (club-pushed updates) — MVP minimal version

**Feature Branch**: `hu-23-event-reprogramming`
**Created**: 2026-10-13 | **Revised**: 2026-10-13 (v2, adds withdrawal)
**Status**: Draft
**Backlog Reference**: HU-23 (backlog: Estimate 5, Priority Media, MVP: Quizás). **Proposal: bring this minimal version into the MVP with priority Alta.** The club pushes event updates to the platform API; withdrawal/restoration is an extension of the original backlog story.
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md)
**API contract**: [Event API contract](../../docs/event-api-contract.md)
**Input**: "As a System Administrator, I want to update the date, time or venue of an event, even if it was already published, and to withdraw an event that will not take place, so that I reflect changes in the schedule and keep the information correct for Socios."

**Why a minimal version**: the club organizes events and pushes source data to the platform (HU-21), so the date, time and venue are no longer typed in by the Administrador. Reprogramming means the club pushes a PUT update to the platform API; the platform applies valid source-field changes immediately and records them for the Administrator's review. The Administrator may adjust class/points during the following 24 hours. Cancellation means withdrawing the event after a club cancellation notice. The platform never calls or polls the club API. Notifications by email (HU-19/20) are not included.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Apply Club-Pushed Event Changes (Priority: P1)

As a System Administrator, I want to review event updates pushed by the club, including changes to an already published event, so that the information Socios see is correct.

**Independent Test**: Publish an event, have the club push a date change to `PUT /api/v1/eventos/{id_interno}`, and verify Socios see the new date in HU-17 right away, the Administrator sees the before/after values and 24-hour review window, and the change is audited.

**Acceptance Scenarios**:

1. **Given** an event in `pending importance definition` or `published` whose start has not passed, **When** the club PUTs an update to `/api/v1/eventos/{id_interno}`, **Then** the platform validates and applies supported changed fields (`fecha_hora`, `lugar`, `descripcion`); the update response and audit identify the changed values.
2. **Given** a published event has a valid date/time or venue update, **When** the platform applies the PUT, **Then** the event stays `published`, Socios see the changes immediately (HU-17, HU-39), and the Administrator can review the before/after values and adjust its class/points within 24 hours.
3. **Given** a PUT contains no changes, **When** it is processed, **Then** the platform returns success and reports that the event is up to date without changing it.
4. **Given** an update changes `tipo` or attempts to change `titulo` or `id_externo`, **When** it is submitted, **Then** the platform rejects it (`422` for a type change) and leaves the event unchanged.
5. **Given** a published event is cancelled, **When** the club posts a cancellation notice to `/api/v1/eventos/{id_interno}/cancelacion`, **Then** nothing changes automatically, the event is flagged in the admin view, and the action "Retirar evento" is offered.
6. **Given** an update or cancellation push is unauthorized or structurally invalid, **When** the platform receives it, **Then** it rejects the request, shows the reason to the Administrator, and makes no event changes. The platform does not call the club API.
7. **Given** a PUT that changed the date/time or venue of a published event, **When** it is applied, **Then** the Administrador has 24 hours to adjust the class (Partido) or the points (institutional/amateur event) again, and if they do nothing the current class or points are kept.
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
7. **Given** an event in `pending importance definition` that the club reports as cancelled, **When** the Administrador wants to remove it, **Then** the action is the discard of HU-21, not this withdrawal.
8. **Given** a withdrawal or a restoration, **When** it is stored, **Then** the audit log records who, when, the reason and the state change.
9. **Given** a logged-in Dirigente or Socio, **When** they look for these actions, **Then** they are not available and the server rejects the request.

---

### Edge Cases

- **Eligible events for club-pushed updates**: `pending importance definition` or `published` events whose start has not yet passed. Historical, discarded, withdrawn and already started events cannot be updated.
- **Eligible events for withdrawal**: `published` events whose start has not passed. The Administrador can withdraw on a club cancellation notice or another reliable club communication.
- **Concurrency**: two Administradores acting on the same event at once; a later administrative class/points adjustment or withdrawal must detect intervening changes and reload before continuing.
- **Publication lead**: the 48-hour lead applies to the publication, not to a reprogramming. The club can move a published match closer than 48 hours.
- **Pending events**: valid PUT updates do not restart their publication window (HU-21).
- **No notifications**: Socios are not warned by email (HU-19/20 are outside the MVP); they see the change or the disappearance when they open the app.
- **Attendance and scoring**: an event is updateable or withdrawable only before it takes place, so no attendance exists yet and the scores do not change.
- **Venue**: the venue is informative. A Partido is assumed at the club stadium; if the club moves it elsewhere, the Administrador keeps the event as is (the distance model is unchanged).
- **Postponement**: if the club keeps the same event with a new date, it sends a PUT update, not a cancellation notice.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept authenticated club updates via `PUT /api/v1/eventos/{id_interno}` for source fields `fecha_hora`, `lugar`, and `descripcion`; the platform MUST NOT call or poll a club API.
- **FR-002**: System MUST show the Administrator the previous and current values for each applied update; confirmation is not required for the API update itself.
- **FR-003**: System MUST keep the `published` state and reflect valid source-field changes to Socios immediately, without a new publication.
- **FR-004**: System MUST reject a type change or update to fields not editable by PUT and make no changes for an unknown event ID or invalid request.
- **FR-005**: System MUST give the Administrador 24 hours after an applied change to adjust the class or points, and keep the current ones otherwise.
- **FR-006**: System MUST leave a confirmed wave schedule untouched when the new start is not before its general closing; invalidate it when the new start is before the closing and no wave opened; and move the closing to the new start when a wave already opened.
- **FR-007**: System MUST accept a cancellation notice through the proposed `POST /api/v1/eventos/{id_interno}/cancelacion`, flag the event, and offer administrator withdrawal.
- **FR-008**: System MUST let an Administrador withdraw a published event whose start has not passed, with a required reason and a confirmation, moving it to `withdrawn`.
- **FR-009**: System MUST hide a withdrawn event from Socios, void its segmentation and schedule, and keep it out of the scoring and of the attendance load.
- **FR-010**: System MUST let an Administrador restore a withdrawn event whose start has not passed, leaving its schedule void.
- **FR-011**: System MUST audit every club update, cancellation notice, withdrawal and restoration (source/actor, when, reason or previous and new values).
- **FR-012**: System MUST restrict these actions to Administradores, enforced on the server, and prevent concurrent overwrites.

### Key Entities

- **Event**: as in HU-21, plus last refreshed at, the end of the class-or-points adjustment window and the state `withdrawn`.
- **EventChange**: event, changed at, changed by, previous values, new values.
- **EventWithdrawal**: event, withdrawn at, withdrawn by, reason, restored at, restored by.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of applied changes appear in HU-17 immediately and in the audit log with previous and new values.
- **SC-002**: 0 updates persist anything when the request is invalid or the type differs.
- **SC-003**: 0 class or points changes are accepted outside the 24-hour window after an eligible published-event PUT update.
- **SC-004**: 100% of schedule conflicts end in exactly one of the three outcomes of FR-006.
- **SC-005**: 0 withdrawn events are visible to Socios, count in the scoring or accept attendance.
- **SC-006**: 100% of withdrawals and restorations carry a reason or a record in the audit log.

## Assumptions

- The club identifies PUT updates with the platform `id_interno` returned by create/query; `id_externo` remains the club's stable source identity. Cancellation is signaled explicitly; omission from a partial submission is not sufficient evidence.
- Valid PUT updates are applied immediately. The Administrator reviews the recorded changes and may adjust class/points within 24 hours; administrator confirmation is not a precondition for the source update. The cancellation endpoint is proposed in the [Event API contract](../../docs/event-api-contract.md) and must be confirmed with the club because it is not in the PDF.
- For published matches, this story follows HU-23's permission to reschedule inside 48 hours even though the PDF requires a match's new date to remain 48 hours ahead. The [Event API contract](../../docs/event-api-contract.md) records this as an intentional deviation.
- The full original HU-23 lets the Administrador edit the fields by hand. This version does not: the club is the source of truth.
- The withdrawal is not in the original backlog; it was added because a cancelled published event would otherwise stay visible.
- The email notifications of the original HU-23 and HU-22 depend on HU-19/20 and stay out of the MVP.

## Revision Notes

- v1: club-pushed updates with the 24-hour review window and schedule rules.
- v2: added the withdrawal and restoration of cancelled events, explicit cancellation notice handling, and the state `withdrawn`.

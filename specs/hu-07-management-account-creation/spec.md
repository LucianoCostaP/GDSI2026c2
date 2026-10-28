# Feature Specification: Create Admin Account

**Feature Branch**: `hu-07-management-account-creation`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3)
**Status**: Draft
**Backlog Reference**: HU-07 (Estimate: 3, Priority: Alta, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an Admin, I want to create an account for another Admin, so that they can access the management features."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create Admin Account (Priority: P1)

As an Admin, I want to create an account for another Admin, so that they can access the management features.

**Why this priority**: Without it no one beyond the initial Admin can configure events or scoring rules.

**Independent Test**: As an Admin, enter name and email (twice) for a new email and verify an invitation is sent and the account is `pending activation`.

**Acceptance Scenarios**:

1. **Given** an Admin logged in, **When** they enter name and email (typed twice) of a new Admin and confirm, **Then** the account is created in state `pending activation` and an invitation with an activation link, valid 48 hours, is sent to that email.
2. **Given** an email already tied to an active or `pending activation` management account with a valid invitation, **When** the Admin tries to create it, **Then** the system rejects the creation.
3. **Given** an email previously used by an account that was removed, **When** the Admin creates it, **Then** it is treated as a completely new account, with no reactivation or history continuity; the earlier removal audit record is kept separately.
4. **Given** a pending invitation that expired without activation, **When** the Admin creates the same email again, **Then** a new invitation is generated and replaces the previous one (status `replaced`), as if no prior account existed.
5. **Given** the two email entries differ or the format is invalid, **When** the Admin confirms, **Then** creation is blocked with a validation message.

---

### Edge Cases

- **Pending, non-expired invitation** counts as an existing pending account and blocks a new creation (until it expires after 48 hours).
- **Email normalization**: trimmed and compared case-insensitively.
- **Role restriction**: only Admins can create accounts.
- **Wrong recipient**: whoever receives the link can activate the account (HU-08), so the double entry and the 48-hour expiry are the mitigation.
- **Person who is also a Socio**: allowed; accounts are independent.
- **Invitation email failure**: if the invitation cannot be sent, the whole creation is undone: no account and no invitation remain, the Admin sees "No pudimos enviar la invitación. Probá de nuevo." (`EMAIL_DELIVERY_FAILED`) and can retry at once. There is no resend of an invitation that was sent: to correct it, wait for the 48-hour expiry and create the account again.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let an Admin enter name and email (confirmed by typing it twice) for a new Admin account.
- **FR-002**: System MUST reject an email associated with an active account or a pending account with a valid invitation.
- **FR-003**: System MUST treat an email from a previously removed account as a brand-new account, keeping the earlier audit record separate.
- **FR-004**: System MUST send an invitation with a single-use activation link, valid 48 hours, to the entered email upon confirmation.
- **FR-005**: System MUST keep the account `pending activation` until the invitee completes HU-08.
- **FR-006**: System MUST restrict this action to Admins, enforced on the server.
- **FR-007**: System MUST allow re-creating an email whose pending invitation expired, replacing the old invitation.
- **FR-008**: System MUST audit every creation and replacement (who, when, email, club).
- **FR-009**: System MUST create the account in the club of the Admin who creates it (cross-cutting section 9), and MUST reject, as an existing account, an email already used by an account of another club.

### Key Entities

- **ManagementAccount**: name, email (normalized), role (always Admin), state (`pending activation` / `active`).
- **Invitation**: account, token (stored hashed), expiry, status (`valid` / `used` / `expired` / `replaced`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of valid creations produce one `pending activation` account and one invitation email.
- **SC-002**: 0 duplicate active-or-pending accounts exist for the same normalized email (enforced by a database constraint).

## Assumptions

- The first Admin is seeded (cross-cutting section 7).
- Account removal (HU-09) is not in the MVP, so scenario 3 is specified but only testable once HU-09 exists.
- Editing the email of a pending account is not supported; the way to correct it is to wait for the invitation to expire (48 hours) and create the account again.

## Revision Notes (v2)

- Added double email entry, normalization, a 48-hour invitation expiry, audit and server-side authorization. Revoking a pending invitation was dropped: expiry is the only way out.
- Documented the first-Admin seed.
- v3: invitation validity is 48 hours; revoking a pending invitation was dropped.

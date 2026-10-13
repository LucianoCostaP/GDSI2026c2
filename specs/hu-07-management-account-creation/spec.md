# Feature Specification: Create Dirigente / Administrador Account

**Feature Branch**: `hu-07-management-account-creation`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3)
**Status**: Draft
**Backlog Reference**: HU-07 (Estimate: 3, Priority: Alta, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a System Administrator, I want to create an account for a Dirigente or another Administrador, so that they can access the features specific to their role."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create Dirigente / Administrador Account (Priority: P1)

As a System Administrator, I want to create an account for a Dirigente or another Administrador, so that they can access the features specific to their role.

**Why this priority**: Without it no one beyond the initial Administrador can configure events or scoring rules.

**Independent Test**: As an Administrador, enter name, email (twice) and role "Dirigente" for a new email and verify an invitation is sent and the account is `pending activation`.

**Acceptance Scenarios**:

1. **Given** an Administrador logged in, **When** they enter name, email (typed twice) and role (Dirigente or Administrador) of a new user and confirm, **Then** the account is created in state `pending activation` and an invitation with an activation link, valid 48 hours, is sent to that email.
2. **Given** an email already tied to an active or `pending activation` management account with a valid invitation, **When** the Administrador tries to create it, **Then** the system rejects the creation.
3. **Given** an email previously used by an account that was removed, **When** the Administrador creates it, **Then** it is treated as a completely new account, with no reactivation or history continuity; the earlier removal audit record is kept separately.
4. **Given** a pending invitation that expired without activation, **When** the Administrador creates the same email again, **Then** a new invitation is generated and replaces the previous one (status `replaced`), as if no prior account existed.
5. **Given** a logged-in Dirigente, **When** they try to create a management account, **Then** the action is not available and the server rejects the request.
6. **Given** the two email entries differ or the format is invalid, **When** the Administrador confirms, **Then** creation is blocked with a validation message.

---

### Edge Cases

- **Pending, non-expired invitation** counts as an existing pending account and blocks a new creation (until it expires after 48 hours).
- **Email normalization**: trimmed and compared case-insensitively.
- **Role restriction**: only Administradores can create accounts.
- **Wrong recipient**: whoever receives the link can activate the account (HU-08), so the double entry and the 48-hour expiry are the mitigation.
- **Person who is also a Socio**: allowed; accounts are independent.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let an Administrador enter name, email (confirmed by typing it twice) and role for a new account.
- **FR-002**: System MUST reject an email associated with an active account or a pending account with a valid invitation.
- **FR-003**: System MUST treat an email from a previously removed account as a brand-new account, keeping the earlier audit record separate.
- **FR-004**: System MUST send an invitation with a single-use activation link, valid 48 hours, to the entered email upon confirmation.
- **FR-005**: System MUST keep the account `pending activation` until the invitee completes HU-08.
- **FR-006**: System MUST restrict this action to Administradores, enforced on the server.
- **FR-007**: System MUST allow re-creating an email whose pending invitation expired, replacing the old invitation.
- **FR-008**: System MUST audit every creation and replacement (who, when, email, role).

### Key Entities

- **ManagementAccount**: name, email (normalized), role, state (`pending activation` / `active`).
- **Invitation**: account, token (stored hashed), expiry, status (`valid` / `used` / `expired` / `replaced`).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of valid creations produce one `pending activation` account and one invitation email.
- **SC-002**: 0 duplicate active-or-pending accounts exist for the same normalized email (enforced by a database constraint).
- **SC-003**: 0 Dirigente users can create management accounts.

## Assumptions

- The first Administrador is seeded (cross-cutting section 7).
- Account removal (HU-09) is not in the MVP, so scenario 3 is specified but only testable once HU-09 exists.
- Editing the email of a pending account is not supported; the way to correct it is to wait for the invitation to expire (48 hours) and create the account again.

## Revision Notes (v2)

- Added double email entry, normalization, a 48-hour invitation expiry, audit and server-side authorization. Revoking a pending invitation was dropped: expiry is the only way out.
- Documented the first-Administrador seed.
- v3: invitation validity is 48 hours; revoking a pending invitation was dropped.

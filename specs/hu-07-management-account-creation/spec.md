# Feature Specification: Create Dirigente / Administrador Account

**Feature Branch**: `hu-07-management-account-creation`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-07 (Estimate: 3, Priority: Alta, MVP: Yes)
**Input**: User description: "As a System Administrator, I want to create an account for a Dirigente or another Administrador, so that they can access the features specific to their role."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create Dirigente / Administrador Account (Priority: P1)

As a System Administrator, I want to create an account for a Dirigente or another Administrador, so that they can access the features specific to their role.

**Why this priority**: Without a way to create management accounts, no one beyond the initial Administrador can configure events or scoring rules.

**Independent Test**: As an Administrador, enter name, email and role "Dirigente" for a new email and verify an invitation email is sent and the account is `pending activation`.

**Acceptance Scenarios**:

1. **Given** an Administrador logged in, **When** they enter name, email and role (Dirigente or Administrador) of a new user and confirm, **Then** the account is created in state `pending activation` and an invitation with an activation link is sent to that email.
2. **Given** an email already tied to an active or pending management account, **When** the Administrador tries to create it, **Then** the system rejects the creation.
3. **Given** an email previously used by an account that was removed, **When** the Administrador creates it, **Then** it is treated as a completely new account, with no reactivation or history continuity; the earlier removal audit record is kept separately.
4. **Given** a pending invitation that expired without activation, **When** the Administrador creates the same email again, **Then** a new invitation is generated and replaces the previous one, as if no prior account existed.
5. **Given** a logged-in Dirigente, **When** they try to create a management account, **Then** the action is not available to them.

---

### Edge Cases

- **Pending, non-expired invitation**: counts as an existing pending account and blocks a new creation.
- **Role restriction**: only Administradores can create Dirigente/Administrador accounts.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let an Administrador enter name, email and role (Dirigente or Administrador) for a new account.
- **FR-002**: System MUST reject an email associated with an active or pending management account.
- **FR-003**: System MUST treat an email from a previously removed account as a brand-new account, keeping the earlier audit record as a separate historical record.
- **FR-004**: System MUST send an invitation with an activation link to the entered email upon confirmation.
- **FR-005**: System MUST keep the account in `pending activation` until the invitee completes activation (HU-08).
- **FR-006**: System MUST restrict this action to Administradores only.
- **FR-007**: System MUST allow re-creating an email whose pending invitation expired, replacing the old invitation.

### Key Entities

- **ManagementAccount**: name, email, role, state (`pending activation` / `active`).
- **Invitation**: activation link sent to an email. Attributes: account, link/token, expiry, status (valid / used / expired / replaced).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of valid creations produce a `pending activation` account and one invitation email.
- **SC-002**: 0 duplicate active-or-pending accounts exist for the same email at any time.
- **SC-003**: 0 Dirigente users can create management accounts.

## Assumptions

- The invitation validity period is a system setting not defined in the backlog.
- Account removal (HU-09) is not in the MVP, so the "previously removed account" scenario is specified here but only exercisable once HU-09 exists.

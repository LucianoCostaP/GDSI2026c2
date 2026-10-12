# Feature Specification: Activate Dirigente / Administrador Account via Invitation

**Feature Branch**: `hu-08-management-account-activation`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-08 (Estimate: 2, Priority: Media, MVP: Yes)
**Input**: User description: "As an invited Dirigente or Administrador, I want to activate my account from the invitation link, so that I can log in to the system."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Activate Dirigente / Administrador Account via Invitation (Priority: P2)

As an invited Dirigente or Administrador, I want to activate my account from the invitation link, so that I can log in to the system.

**Why this priority**: Completes the management account lifecycle started in HU-07; an invited user cannot log in until activation.

**Independent Test**: Open a valid invitation link and verify the account moves from `pending` to `active` and the user can log in through HU-06.

**Acceptance Scenarios**:

1. **Given** a valid invitation link, **When** the invitee opens it, **Then** their identity is confirmed through the email of the invitation (no DNI or member number required).
2. **Given** the identity was confirmed, **When** activation completes, **Then** the account passes from `pending` to `active` and the user can log in through HU-06.
3. **Given** a link that was already used or has expired, **When** the invitee opens it, **Then** the system informs this and tells them to request a new invitation from an Administrador.

---

### Edge Cases

- **Single use**: a link works once; reopening it after activation shows the "already used" message.
- **Replaced invitation**: a link replaced by a newer invitation (HU-07) is treated as unusable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST confirm the invitee's identity through the invitation's email, without requiring DNI or member number.
- **FR-002**: System MUST change the account state from `pending` to `active` upon successful confirmation.
- **FR-003**: System MUST allow login through HU-06 once the account is `active`.
- **FR-004**: System MUST inform the user when the link was already used or expired, and that a new invitation must be requested from an Administrador.

### Key Entities

- **Invitation** and **ManagementAccount**: as in HU-07.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of valid links activate the account on first use.
- **SC-002**: 100% of used, expired or replaced links are rejected with the corresponding message.

## Assumptions

- The way the invitee proves control of the email is the link itself; no additional factor is required by the backlog.

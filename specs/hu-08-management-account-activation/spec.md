# Feature Specification: Activate Admin Account via Invitation

**Feature Branch**: `hu-08-management-account-activation`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3)
**Status**: Draft
**Backlog Reference**: HU-08 (Estimate: 2, Priority: Media, MVP: Yes). Note: HU-07 has no value without this story; consider raising it to Alta.
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an invited Admin, I want to activate my account from the invitation link, so that I can log in to the system."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Activate Admin Account via Invitation (Priority: P2)

As an invited Admin, I want to activate my account from the invitation link, so that I can log in to the system.

**Why this priority**: Completes the management account lifecycle started in HU-07.

**Independent Test**: Open a valid invitation link and verify the account moves from `pending activation` to `active` and the user can log in through HU-06.

**Acceptance Scenarios**:

1. **Given** a valid invitation link, **When** the invitee opens it, **Then** their identity is confirmed through the email of the invitation (no DNI or member number required) and the page shows the invited email masked (format in cross-cutting section 3, for example `j***@gmail.com`).
2. **Given** the identity was confirmed, **When** activation completes, **Then** the account passes from `pending activation` to `active`, the invitation becomes `used`, and the user is sent to the management login (HU-06).
3. **Given** a link that was already used, has expired or was replaced, **When** the invitee opens it, **Then** the system informs this and tells them to request a new invitation from an Admin.

---

### Edge Cases

- **Single use**: reopening the link after activation shows the "already used" message.
- **Replaced invitation**: treated as unusable.
- **Token handling**: the token is random (at least 128 bits), stored hashed, and never written to logs.
- **Race**: two simultaneous opens of the same link activate once; the second gets "already used".

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST confirm the invitee's identity through the invitation's email, without requiring DNI or member number.
- **FR-002**: System MUST change the account state from `pending activation` to `active` upon successful confirmation, atomically with marking the invitation `used`.
- **FR-003**: System MUST allow login through HU-06 once the account is `active`.
- **FR-004**: System MUST inform the user when the link was used, expired or replaced, and that a new invitation must be requested from an Admin.
- **FR-005**: System MUST audit every activation.

### Key Entities

- **Invitation** and **ManagementAccount**: as in HU-07.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of valid links activate the account on first use.
- **SC-002**: 100% of used, expired or replaced links are rejected with the corresponding message.

## Assumptions

- Possession of the link proves control of the email; no additional factor at activation (the first login still needs a code, HU-06). Consequence: a mistyped email gives access to whoever receives it, which HU-07 mitigates with the double entry of the email and the 48-hour expiry (there is no revocation).

## Revision Notes (v2)

- Invitation validity is 48 hours. Added token properties, atomicity and race behavior, and the priority note.
- v3: invitation validity is 48 hours; no revoked state.

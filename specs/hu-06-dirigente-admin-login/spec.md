# Feature Specification: Admin Login with Emailed Access Code

**Feature Branch**: `hu-06-dirigente-admin-login`
**Created**: 2026-10-11 | **Revised**: 2026-10-12 (v2)
**Status**: Draft
**Backlog Reference**: HU-06 (Estimate: 3, Priority: Alta, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an Admin, I want to log in with an access code sent to the email the club has registered, so that I can access my management features."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Admin Login with Emailed Access Code (Priority: P1)

As an Admin, I want to log in with an access code sent to the email the club has registered, so that I can access my management features.

**Why this priority**: Management accounts are the only way to configure events, rules and rankings.

**Independent Test**: From the initial screen choose "Admin access", enter an active management email, enter the code and verify redirection to the Admin home screen.

**Acceptance Scenarios**:

1. **Given** the initial screen (delivered by HU-05) with the two accesses, **When** the user chooses "Admin access", **Then** the management login form is shown.
2. **Given** an active Admin account, **When** the user enters their email, **Then** an access code is sent to that email.
3. **Given** a code was sent, **When** the user enters the correct, non-expired code, **Then** the Admin is logged in and lands on the Admin home screen.
4. **Given** an incorrect or expired code, **When** it is submitted, **Then** login is denied and the user can request a new code.
5. **Given** an email that does not belong to an active management account (unknown, `pending activation`), **When** it is submitted, **Then** a generic error message is shown, no code is sent, and the message does not reveal which case applies.
6. **Given** a DNI or member number typed in this form, **When** it is submitted, **Then** it is rejected as an invalid email.

---

### Edge Cases

- **Email only**: DNI and member number MUST NOT be accepted.
- **Pending accounts**: an account `pending activation` (HU-08) cannot log in and gets the generic message.
- **Dual identity**: a person who is also a Socio uses each door separately; no account is shared.
- **Code rules**: same as HU-05 (expiry, single use, attempts, cooldown, lockout).
- **Email delivery failure**: if the email cannot be sent, the system shows "No pudimos enviar el código. Probá de nuevo en un minuto." (`EMAIL_DELIVERY_FAILED`), the code is discarded and can never be used, and a new one can be requested right away: the 60-second cooldown counts only codes that were actually sent (cross-cutting section 3).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept only an email as identifier in the management login.
- **FR-002**: System MUST send an access code to the account's email once the credential is validated.
- **FR-003**: System MUST let the user enter the code, expire it after the configured time and limit attempts.
- **FR-004**: System MUST allow requesting a resend when the code is incorrect or expired.
- **FR-005**: System MUST redirect the Admin to the Admin home screen.
- **FR-006**: System MUST show a generic error when the email is not an active management account.
- **FR-007**: System MUST create a server-side session on success.

### Key Entities

- **ManagementAccount**: name, email, role, state (`pending activation` / `active`).
- **AccessCode** and **Session**: as in HU-05.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of valid logins land on the Admin home screen.
- **SC-002**: 100% of unknown, pending, wrong-code or expired attempts are rejected without revealing the account state.

## Assumptions

- The content of the Admin home screen is out of scope here; the shell and homes are bootstrap work (cross-cutting section 7).
- The "email registered in the club" for a management account is the email entered in HU-07.

## Revision Notes (v2)

- The generic error now covers pending accounts, removing an enumeration path.
- The initial screen is owned by HU-05; this story only depends on it.
- Fixed the backlog wording that said "El socio ingresa el código" (it is the management user).

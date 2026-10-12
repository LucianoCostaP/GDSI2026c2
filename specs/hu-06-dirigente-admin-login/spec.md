# Feature Specification: Dirigente / Administrador Login with Emailed Access Code

**Feature Branch**: `hu-06-dirigente-admin-login`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-06 (Estimate: 1, Priority: Alta, MVP: Yes)
**Input**: User description: "As a Dirigente or System Administrator, I want to log in with an access code sent to the email the club has registered, so that I can access my management features."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dirigente / Administrador Login with Emailed Access Code (Priority: P1)

As a Dirigente or System Administrator, I want to log in with an access code sent to the email the club has registered, so that I can access my management features.

**Why this priority**: Management accounts are the only way to configure events, rules and rankings; the whole admin side of the MVP depends on this login.

**Independent Test**: From the initial screen choose "Acceso Dirigente/Administrador", enter an active management email, enter the received code and verify redirection to the home screen matching the account's role.

**Acceptance Scenarios**:

1. **Given** the initial screen with the two accesses, **When** the user chooses "Acceso Dirigente/Administrador", **Then** the management login form is shown.
2. **Given** an active Dirigente or Administrador account, **When** the user enters their email, **Then** an access code is sent to the email registered in the club.
3. **Given** a code was sent, **When** the user enters the correct, non-expired code, **Then** the system detects whether the account is Dirigente or Administrador and redirects to the home screen of that role.
4. **Given** an incorrect or expired code, **When** it is submitted, **Then** login is denied and the user can request a new code.
5. **Given** incorrect credentials, **When** they are submitted, **Then** an error message is shown.

---

### Edge Cases

- **Email only**: DNI and member number MUST NOT be accepted in this login.
- **Pending accounts**: an account still pending activation (HU-08) cannot log in.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept only an email as identifier in the management login.
- **FR-002**: System MUST send an access code to the registered email once the credential is validated.
- **FR-003**: System MUST let the user enter the code, and MUST expire codes after a defined time.
- **FR-004**: System MUST allow requesting a resend when the code is incorrect or expired.
- **FR-005**: System MUST distinguish Dirigente from Administrador and redirect each to their own home screen.
- **FR-006**: System MUST show an error message when credentials are incorrect.

### Key Entities

- **ManagementAccount**: Dirigente or Administrador account. Attributes: name, email, role, state (pending / active).
- **AccessCode**: as in HU-05.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of valid logins land on the home screen of the correct role.
- **SC-002**: 100% of incorrect credentials or invalid codes are rejected with an error message.

## Assumptions

- The content of each role's home screen is out of scope; it is built by the stories that use it.
- Code expiry duration is a system setting not defined in the backlog.

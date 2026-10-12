# Feature Specification: Socio Login with Emailed Access Code

**Feature Branch**: `hu-05-socio-login`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-05 (Estimate: 1, Priority: Alta, MVP: Yes)
**Input**: User description: "As a Socio of the club, I want to log in by requesting an access code sent to the email the club has registered, so that I can access my scoring, ranking and reservation features."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Socio Login with Emailed Access Code (Priority: P1)

As a Socio of the club, I want to log in by requesting an access code sent to the email the club has registered, so that I can access my scoring, ranking and reservation features.

**Why this priority**: Login is required to reach every Socio feature; without it the rest of the Socio view is unreachable.

**Independent Test**: From the initial screen choose "Acceso Socio", enter a DNI of an activated Socio, receive the code at the registered email, enter it and verify access is granted.

**Acceptance Scenarios**:

1. **Given** the initial screen with two differentiated accesses, "Acceso Socio" and "Acceso Dirigente/Administrador", **When** the user chooses "Acceso Socio", **Then** the Socio login form is shown.
2. **Given** an activated Socio, **When** they enter their DNI, member number or email, **Then** the system sends an access code to the email registered in the club.
3. **Given** a code was sent, **When** the Socio enters the correct, non-expired code, **Then** the Socio is logged in.
4. **Given** an incorrect or expired code, **When** the Socio submits it, **Then** login is denied and the Socio can request that a new code be sent.
5. **Given** an identifier belonging to a Socio whose account is not activated, **When** it is submitted, **Then** the Socio is informed and redirected to the activation flow (HU-01).

---

### Edge Cases

- **Identifier types**: DNI, member number and email are all accepted in the same field.
- **Code expiry**: an expired code is rejected exactly like an incorrect one.
- **Unknown identifier**: not specified in the backlog; a generic error is shown without revealing whether the identifier exists (to confirm).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST present an initial screen with two differentiated accesses: "Acceso Socio" and "Acceso Dirigente/Administrador".
- **FR-002**: System MUST accept DNI, member number or email as identifier in the Socio login.
- **FR-003**: System MUST send an access code to the email registered in the club once the identifier is validated.
- **FR-004**: System MUST let the Socio enter the received code to continue.
- **FR-005**: System MUST expire access codes after a defined time.
- **FR-006**: System MUST allow requesting a resend when the code is incorrect or expired.
- **FR-007**: System MUST inform and redirect to the activation flow when the account is not activated.

### Key Entities

- **Socio**: as in HU-01; here the relevant attributes are identifiers (DNI, member number, email) and account state.
- **AccessCode**: one-time code sent to the registered email. Attributes: recipient, creation time, expiry time, status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of logins with a valid, non-expired code succeed; 100% with an incorrect or expired code are rejected.
- **SC-002**: A Socio with a non-activated account never obtains a session and is always redirected to activation.

## Assumptions

- The code expiry duration is a system setting; its value is not defined in the backlog.
- The initial screen (referred to as HU-00 in HU-11) is delivered as part of this story, since its acceptance criteria describe it.

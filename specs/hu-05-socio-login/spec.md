# Feature Specification: Socio Login with Emailed Access Code (and Initial Screen)

**Feature Branch**: `hu-05-socio-login`
**Created**: 2026-10-11 | **Revised**: 2026-10-12 (v2)
**Status**: Draft
**Backlog Reference**: HU-05 (Estimate: 1, Priority: Alta, MVP: Yes). Re-estimate: includes the initial screen (HU-00), code delivery and session creation that HU-06 also reuses.
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Socio of the club, I want to log in by requesting an access code sent to the email the club has registered, so that I can access my scoring, ranking and reservation features."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Socio Login with Emailed Access Code (Priority: P1)

As a Socio of the club, I want to log in by requesting an access code sent to the email the club has registered, so that I can access my scoring, ranking and reservation features.

**Why this priority**: Login is required to reach every Socio feature.

**Independent Test**: From the initial screen choose "Acceso Socio", enter the DNI of an activated Socio, receive the code, enter it and verify access to the Socio home.

**Acceptance Scenarios**:

1. **Given** the initial screen (HU-00) with two differentiated accesses, "Acceso Socio" and "Acceso Dirigente/Administrador", **When** the user chooses "Acceso Socio", **Then** the Socio login form is shown.
2. **Given** an activated Socio, **When** they enter their DNI, member number or email, **Then** the system sends an access code to the registered email and shows that email partially masked.
3. **Given** a code was sent, **When** the Socio enters the correct, non-expired code, **Then** the Socio is logged in and lands on the Socio home.
4. **Given** an incorrect or expired code, **When** the Socio submits it, **Then** login is denied and the Socio can request a new code.
5. **Given** an identifier belonging to a Socio whose account is not activated, **When** it is submitted, **Then** the Socio is informed and redirected to the activation flow (HU-01).
6. **Given** an identifier that matches no Socio, **When** it is submitted, **Then** a generic message is shown that does not reveal whether the identifier exists, and no code is sent.
7. **Given** 5 failed attempts on a code, **When** the next attempt is made, **Then** the code is invalid and the identifier is temporarily locked (cross-cutting section 3).
8. **Given** an activated Socio with overdue fees, **When** they log in with a valid code, **Then** login succeeds (fees do not block access; their ranking status is explained in HU-14).

---

### Edge Cases

- **Identifier types**: DNI, member number and email in the same field. If an identifier matches different Socios by different types, the Socio chooses the type. If an email is shared by several Socios, the Socio must type a DNI or member number instead.
- **Code expiry**: an expired code is rejected exactly like an incorrect one.
- **Missing email in club data**: no code is sent; the Socio is told to contact the club.
- **Authorization**: this door never grants management access.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST present an initial screen with two differentiated accesses: "Acceso Socio" and "Acceso Dirigente/Administrador".
- **FR-002**: System MUST accept DNI, member number or email as identifier in the Socio login.
- **FR-003**: System MUST send an access code to the registered email once the identifier is validated.
- **FR-004**: System MUST let the Socio enter the received code to continue.
- **FR-005**: System MUST expire access codes after the configured time (default 10 minutes), make them single use and limit attempts.
- **FR-006**: System MUST allow requesting a resend when the code is incorrect or expired, respecting the cooldown.
- **FR-007**: System MUST inform and redirect to the activation flow when the account is not activated.
- **FR-008**: System MUST create a server-side session on success and apply the session limits.
- **FR-009**: System MUST NOT reveal whether an unknown identifier exists.

### Key Entities

- **Socio**: identifiers (DNI, member number, email) and account state.
- **AccessCode**: purpose (login), recipient, created at, expiry, attempts, status.
- **Session**: user, role, created at, last activity, revoked at.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of logins with a valid, non-expired code succeed; 100% with an incorrect, expired or used code are rejected.
- **SC-002**: A Socio with a non-activated account never obtains a session and is always redirected to activation.
- **SC-003**: 95% of codes are delivered in under 30 seconds in load tests.

## Assumptions

- The initial screen (HU-00 in HU-11) is delivered by this story; HU-06 reuses it.
- The code and session mechanism built here is reused by HU-01 and HU-06.
- Fee status does not block login. [NEEDS CLARIFICATION: confirm with the club.]

## Revision Notes (v2)

- Added code parameters, lockout, masked email, ambiguity and shared-email rules, and the overdue-fee decision.
- Made the generic message for unknown identifiers mandatory.

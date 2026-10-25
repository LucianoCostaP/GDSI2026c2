# Feature Specification: Identity Verification and Activation by DNI / Socio Number

**Feature Branch**: `hu-01-identity-verification`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3)
**Status**: Draft
**Backlog Reference**: HU-01 (Estimate: 3, Priority: Alta, MVP: Yes). Re-estimate: scope now includes the email-code step that completes activation.
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md)
**Input**: "As a Socio accessing the system for the first time, I want to verify my identity by entering my DNI or member number, so that I can activate my account."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Identity Verification and Activation (Priority: P1)

As a Socio accessing the system for the first time, I want to verify my identity by entering my DNI or member number, so that I can activate my account.

**Why this priority**: Entry gate for every Socio feature: no Socio can log in or see their score until their identity is checked against the club data and the account is activated.

**Independent Test**: Enter the DNI of a Socio in good standing with no activated account, receive the code at the registered email, enter it and verify the account becomes `activated`. Then try an unknown DNI, an overdue Socio and an already activated Socio and verify the three different messages.

**Acceptance Scenarios**:

1. **Given** a Socio exists in the club data, has no activated account and has fees up to date, **When** the Socio enters their DNI or member number, **Then** the identifier is validated and the system sends an activation code to the email registered in the club (the "next verification step").
2. **Given** an activation code was sent, **When** the Socio enters the correct, non-expired code, **Then** the account becomes `activated` and the Socio is redirected to login (HU-05) with a confirmation message.
3. **Given** an incorrect or expired code, **When** it is submitted, **Then** activation is denied and the Socio can request a new code (rules in cross-cutting section 3).
4. **Given** an identifier that does not exist in the club data, **When** it is submitted, **Then** the message "No encontramos ese DNI o N° de socio." (`MEMBER_NOT_FOUND`) is shown and the flow does not advance.
5. **Given** a Socio who exists but does not have fees up to date, **When** the Socio submits their identifier, **Then** the system informs that the account cannot be activated and states why (fees pending), without showing amounts.
6. **Given** a Socio who already has an activated account, **When** the Socio submits their identifier, **Then** the system informs that the account is already activated and redirects to login (HU-05).
7. **Given** an identifier that matches the DNI of one Socio and the member number of another, **When** it is submitted, **Then** the system asks the Socio to choose the identifier type before continuing.
8. **Given** a Socio with no email registered in the club, **When** they pass the fee check, **Then** the system informs that the club has no email on file and that activation must be solved with the club; no code is sent.

---

### Edge Cases

- **Either identifier**: DNI and member number are both accepted in the same field.
- **Empty or malformed input**: blocked with a validation message before any lookup.
- **Distinct messages**: each case has its own text and error code, and tests compare the exact text:

  | Case | Code | Message |
  |---|---|---|
  | Not found (scenario 4) | `MEMBER_NOT_FOUND` | "No encontramos ese DNI o N° de socio." |
  | Overdue fees (scenario 5) | `FEES_OVERDUE` | "No podés activar tu cuenta porque tenés cuotas pendientes. Regularizá tu situación con el club." |
  | Already activated (scenario 6) | `ACCOUNT_ALREADY_ACTIVATED` | "Tu cuenta ya está activada. Iniciá sesión." |
  | Missing email (scenario 8) | `NO_EMAIL_ON_FILE` | "El club no tiene un email registrado para vos. Comunicate con el club para activar tu cuenta." |

- **Email delivery failure**: if the email cannot be sent, the system shows "No pudimos enviar el código. Probá de nuevo en un minuto." (`EMAIL_DELIVERY_FAILED`), the code is discarded and can never be used, and a new one can be requested right away: the 60-second cooldown counts only codes that were actually sent (cross-cutting section 3).
- **Socio de baja**: a Socio the club marked inactive (HU-43) is treated as not found.
- **Abuse**: lookups are rate limited (cross-cutting section 3) and messages never include personal data.
- **Fee status source**: the fee status comes from the latest roster received from the club (HU-43); if the data is older than the staleness limit, the check still runs and the data age is recorded.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a DNI or a member number as identifier in one field.
- **FR-002**: System MUST validate the identifier against the club data.
- **FR-003**: System MUST send an activation code to the registered email only when the Socio exists, has no activated account and has fees up to date.
- **FR-004**: System MUST show "No encontramos ese DNI o N° de socio." (`MEMBER_NOT_FOUND`) when the identifier does not exist or belongs to a Socio de baja.
- **FR-005**: System MUST inform that the account cannot be activated, and why, when fees are not up to date.
- **FR-006**: System MUST inform that the account is already activated and redirect to login when an activated account exists.
- **FR-007**: System MUST mark the account `activated` once the correct code is entered, and only then.
- **FR-008**: System MUST resolve identifier ambiguity by asking for the identifier type.
- **FR-009**: System MUST handle a missing registered email without sending any code.
- **FR-010**: System MUST rate limit lookups and code requests.

### Key Entities

- **Socio**: DNI, member number, registered email, fee status, account state (`not activated` / `activated`).
- **AccessCode** (purpose: activation): recipient, created at, expiry, attempts, status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Each of the eight scenarios produces exactly the behavior above in automated tests.
- **SC-002**: 0 Socios with overdue fees or unknown identifiers receive a code.
- **SC-003**: 0 accounts become `activated` without a valid code.

## Assumptions

- "Next verification step" is the email code (confirmed by the product owner).
- Activating means proving control of the registered email; the system does not collect passwords (login is by code, HU-05).
- The club data are read-only for this story.

## Revision Notes (v2)

- Resolved the undefined "next verification step" and completed activation inside this story.
- Added scenarios for ambiguous identifiers, missing email, wrong code, and abuse limits.
- v3: confirmed that the next verification step is the email code.

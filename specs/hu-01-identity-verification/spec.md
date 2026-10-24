# Feature Specification: Identity Verification and Activation by DNI / Member Number

**Feature Branch**: `hu-01-identity-verification`
**Created**: 2026-10-11 | **Revised**: 2026-10-13 (v3)
**Status**: Draft
**Backlog Reference**: HU-01 (Estimate: 3, Priority: Alta, MVP: Yes). Re-estimate: scope now includes the email-code step that completes activation.
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md)
**Input**: "As a Member accessing the system for the first time, I want to verify my identity by entering my DNI or member number, so that I can start the activation process of my account."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Identity Verification and Activation (Priority: P1)

As a Member accessing the system for the first time, I want to verify my identity by entering my DNI or member number, so that I can start the activation process of my account.

**Why this priority**: Entry gate for every Member feature: no Member can log in or see their score until their identity is checked against the club data and the account is activated.

**Independent Test**: Enter the DNI of a Member in good standing with no activated account, receive the code at the registered email, enter it and verify the account becomes `activated`. Then try an unknown DNI, an overdue Member and an already activated Member and verify the three different messages.

**Acceptance Scenarios**:

1. **Given** a Member exists in the club data, has no activated account and has fees up to date, **When** the Member enters their DNI or member number, **Then** the identifier is validated and the system sends an activation code to the email registered in the club (the "next verification step").
2. **Given** an activation code was sent, **When** the Member enters the correct, non-expired code, **Then** the account becomes `activated` and the Member is redirected to login (HU-05) with a confirmation message.
3. **Given** an incorrect or expired code, **When** it is submitted, **Then** activation is denied and the Member can request a new code (rules in cross-cutting section 3).
4. **Given** an identifier that does not exist in the club data, **When** it is submitted, **Then** a clear error message is shown and the flow does not advance.
5. **Given** a Member who exists but does not have fees up to date, **When** the Member submits their identifier, **Then** the system informs that the account cannot be activated and states why (fees pending), without showing amounts.
6. **Given** a Member who already has an activated account, **When** the Member submits their identifier, **Then** the system informs that the account is already activated and redirects to login (HU-05).
7. **Given** an identifier that matches the DNI of one Member and the member number of another, **When** it is submitted, **Then** the system asks the Member to choose the identifier type before continuing.
8. **Given** a Member with no email registered in the club, **When** they pass the fee check, **Then** the system informs that the club has no email on file and that activation must be solved with the club; no code is sent.

---

### Edge Cases

- **Either identifier**: DNI and member number are both accepted in the same field.
- **Empty or malformed input**: blocked with a validation message before any lookup.
- **Distinct messages**: not found, overdue fees, already activated and missing email MUST show different messages.
- **Abuse**: lookups are rate limited (cross-cutting section 3) and messages never include personal data.
- **Fee status source**: the fee status comes from the last synchronization (HU-N2); if the data is older than the staleness limit, the check still runs and the data age is recorded.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a DNI or a member number as identifier in one field.
- **FR-002**: System MUST validate the identifier against the club data.
- **FR-003**: System MUST send an activation code to the registered email only when the Member exists, has no activated account and has fees up to date.
- **FR-004**: System MUST show a clear error when the identifier does not exist.
- **FR-005**: System MUST inform that the account cannot be activated, and why, when fees are not up to date.
- **FR-006**: System MUST inform that the account is already activated and redirect to login when an activated account exists.
- **FR-007**: System MUST mark the account `activated` once the correct code is entered, and only then.
- **FR-008**: System MUST resolve identifier ambiguity by asking for the identifier type.
- **FR-009**: System MUST handle a missing registered email without sending any code.
- **FR-010**: System MUST rate limit lookups and code requests.

### Key Entities

- **Member**: DNI, member number, registered email, fee status, account state (`not activated` / `activated`).
- **AccessCode** (purpose: activation): recipient, created at, expiry, attempts, status.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Each of the eight scenarios produces exactly the behavior above in automated tests.
- **SC-002**: 0 Members with overdue fees or unknown identifiers receive a code.
- **SC-003**: 0 accounts become `activated` without a valid code.

## Assumptions

- "Next verification step" is the email code (confirmed by the product owner).
- Activating means proving control of the registered email; the system does not collect passwords (login is by code, HU-05).
- The club data are read-only for this story.

## Revision Notes (v2)

- Resolved the undefined "next verification step" and completed activation inside this story.
- Added scenarios for ambiguous identifiers, missing email, wrong code, and abuse limits.
- v3: confirmed that the next verification step is the email code.

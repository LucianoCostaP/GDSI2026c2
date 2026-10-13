# Feature Specification: Identity Verification by DNI / Member Number

**Feature Branch**: `hu-01-identity-verification`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-01 (Estimate: 3, Priority: Alta, MVP: Yes)
**Input**: User description: "As a Socio accessing the system for the first time, I want to verify my identity by entering my DNI or member number, so that I can activate my account."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Identity Verification by DNI / Member Number (Priority: P1)

As a Socio accessing the system for the first time, I want to verify my identity by entering my DNI or member number, so that I can activate my account.

**Why this priority**: Entry gate for every Socio feature: no Socio can activate an account, log in or see their score until their identity is checked against the club database.

**Independent Test**: Enter the DNI of a Socio in good standing who has no activated account and verify the flow advances to the log-in screen; then enter an unknown DNI and verify a clear error is shown.

**Acceptance Scenarios**:

1. **Given** a Socio exists in the club database, has no activated account and has fees up to date, **When** the Socio enters their DNI or member number, **Then** the identifier is validated and the flow advances to the log-in step.
2. **Given** an identifier that does not exist in the club database, **When** it is submitted, **Then** a clear error message is shown and the flow does not advance.
3. **Given** a Socio who exists but does not have fees up to date, **When** the Socio submits their identifier, **Then** the system informs that the account cannot be activated and states why.
4. **Given** a Socio who already has an activated account, **When** the Socio submits their identifier, **Then** the system informs that the account is already activated and redirects to login (HU-05).

---

### Edge Cases

- **Either identifier**: DNI and member number are both accepted in the same field.
- **Empty input**: submitting without an identifier is blocked with a validation message.
- **Overdue fees vs. unknown identifier**: the two failures MUST show different messages (not found vs. cannot activate due to fees).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept a DNI or a member number as identifier.
- **FR-002**: System MUST validate the identifier against the club database.
- **FR-003**: System MUST advance to the next verification step only when the Socio exists, has no activated account and has fees up to date.
- **FR-004**: System MUST show a clear error when the identifier does not exist in the club database.
- **FR-005**: System MUST inform the Socio that the account cannot be activated, and why, when fees are not up to date.
- **FR-006**: System MUST inform the Socio that the account is already activated and redirect to login when an activated account exists.

### Key Entities

- **Socio**: person registered in the club database. Attributes: DNI, member number, fee status (up to date / overdue), account state (not activated / activated).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the four validation outcomes (advance, not found, overdue fees, already activated) produce exactly the behavior described above.
- **SC-002**: 0 Socios with overdue fees or unknown identifiers advance to the next verification step.

## Assumptions

- The club database is the source of truth and is read-only for this story.

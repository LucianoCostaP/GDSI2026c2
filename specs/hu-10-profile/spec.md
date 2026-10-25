# Feature Specification: Access the Profile

**Feature Branch**: `hu-10-profile`
**Created**: 2026-10-25 (v1)
**Status**: Draft
**Backlog Reference**: HU-10 (Estimate: 2, Priority: Baja, MVP: Yes)
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md), [data contract](../_shared/data-contract.md)
**Input**: "As an authenticated user (Socio or Admin), I want to access my profile from a visible button in the system, so that I can see my account data."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Access the Profile (Priority: P3)

**Why this priority**: Lets users check the data the system holds about them. It is low priority because it shows read-only data used elsewhere.

**Independent Test**: Log in as a Socio and as an Admin, open "Mi Perfil" from two different screens and verify each sees their own data, read-only. Log out and verify the profile is not reachable.

**Acceptance Scenarios**:

1. **Given** a logged-in user on any screen, **When** they look at the global navigation menu, **Then** a "Mi Perfil" button is visible.
2. **Given** a logged-in Socio, **When** they open "Mi Perfil", **Then** they see their name, DNI, member number, registered email, fee status (al día / en mora) and account state, as received from the club (HU-43).
3. **Given** a logged-in Admin, **When** they open "Mi Perfil", **Then** they see their name, email and role.
4. **Given** the profile, **When** the user interacts with it, **Then** it is read-only. A Socio who finds wrong data is told to contact the club, which is the source of truth.
5. **Given** a user without a session, **When** they try to open the profile, **Then** the button is not shown and the server rejects the request.

---

### Edge Cases

- **Only one's own profile**: the profile shows the data of the session's user; there is no way to request another user's profile.
- **Data freshness**: a Socio's data is the latest received from the club.
- **No other data**: the profile does not show distance, birth date or other scoring inputs; the score lives in HU-14 and HU-16.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST show a "Mi Perfil" access in the global navigation menu on every screen once logged in.
- **FR-002**: System MUST show the profile of the session's user, with the fields of scenarios 2 and 3 for each role.
- **FR-003**: System MUST present the profile as read-only.
- **FR-004**: System MUST require a valid session, enforced on the server.

### Key Entities

- **User** and **Socio**: as in HU-05, HU-06 and the data contract; no new data.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of logged-in users reach their own profile from any screen.
- **SC-002**: 0 requests without a valid session obtain profile data.

## Assumptions

- The global navigation menu is part of the application shell (cross-cutting section 7), shared with HU-11.

## Implementation Status

`GET /me` already returns the session's user (`id`, `member_id`, `name`, `email`, `role`). The Socio fields of scenario 2 (DNI, member number, fee status, account state) and the screen are still missing.

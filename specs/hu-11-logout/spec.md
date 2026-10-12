# Feature Specification: Logout

**Feature Branch**: `hu-11-logout`
**Created**: 2026-10-11
**Status**: Draft
**Backlog Reference**: HU-11 (Estimate: 1, Priority: Alta, MVP: Yes)
**Input**: User description: "As an authenticated user (Socio, Dirigente or Administrador), I want to log out from an access available on every screen, so that I can leave the system securely."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Logout (Priority: P1)

As an authenticated user (Socio, Dirigente or Administrador), I want to log out from an access available on every screen, so that I can leave the system securely.

**Why this priority**: Basic session security for all roles, especially on shared devices.

**Independent Test**: Log in with any role, use the global menu to log out, then press the browser's back button and verify protected screens are not accessible.

**Acceptance Scenarios**:

1. **Given** a logged-in user on any screen, **When** they look at the global navigation menu, **Then** a "Cerrar Sesión" option is available.
2. **Given** the user confirms logout, **When** the action completes, **Then** the active session is ended and the user is redirected to the initial screen (HU-00).
3. **Given** a session was closed, **When** the user uses the browser's back button, **Then** protected screens are not accessible without logging in again.

---

### Edge Cases

- **Not logged in**: the logout access is neither visible nor reachable.
- **All roles**: behavior is identical for Socio, Dirigente and Administrador.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide "Cerrar Sesión" in a global navigation menu visible on every screen once logged in.
- **FR-002**: System MUST end the active session upon confirmation and redirect to the initial screen.
- **FR-003**: System MUST prevent access to protected screens after logout, including through the browser's back navigation.

### Key Entities

- **Session**: active authenticated session of a user. Attributes: user, role, state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of logouts end the session and redirect to the initial screen.
- **SC-002**: 0 protected screens are reachable after logout without a new login.

## Assumptions

- HU-00 is the initial screen with the two accesses described in HU-05; it has no story of its own in the backlog.

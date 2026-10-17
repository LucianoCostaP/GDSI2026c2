# Feature Specification: Logout

**Feature Branch**: `hu-11-logout`
**Created**: 2026-10-11 | **Revised**: 2026-10-12 (v2)
**Status**: Draft
**Backlog Reference**: HU-11 (Estimate: 1, Priority: Alta, MVP: Yes). Re-estimate: depends on the global navigation shell.
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an authenticated user (Member, Admin), I want to log out from an access available on every screen, so that I can leave the system securely."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Logout (Priority: P1)

As an authenticated user, I want to log out from an access available on every screen, so that I can leave the system securely.

**Why this priority**: Basic session security for all roles, especially on shared devices.

**Independent Test**: Log in with any role, use the global menu to log out, press the browser's back button and verify protected screens are not accessible; verify the old session token no longer works.

**Acceptance Scenarios**:

1. **Given** a logged-in user on any screen, **When** they look at the global navigation menu, **Then** a "Cerrar Sesión" option is available.
2. **Given** the user confirms logout, **When** the action completes, **Then** the current session is revoked on the server and the user is redirected to the initial screen (HU-00, delivered by HU-05).
3. **Given** a session was closed, **When** the user uses the browser's back button or reuses the old session token, **Then** protected screens and the API are not accessible without logging in again.
4. **Given** a session that exceeded the idle timeout or the absolute limit, **When** the user acts, **Then** they are sent to the initial screen with an "expired session" message.

---

### Edge Cases

- **Not logged in**: the logout access is neither visible nor reachable.
- **All roles**: identical behavior for Member, Admin.
- **Scope**: logout ends the current session only; other devices keep theirs.
- **Cache**: protected pages are served with no-store caching so the back button cannot show them.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide "Cerrar Sesión" in a global navigation menu visible on every screen once logged in.
- **FR-002**: System MUST revoke the current session on the server upon confirmation and redirect to the initial screen.
- **FR-003**: System MUST prevent access to protected screens after logout, including browser back navigation and reuse of the old token.
- **FR-004**: System MUST end sessions after the idle timeout (default 30 minutes) and the absolute limit (default 12 hours).

### Key Entities

- **Session**: user, role, created at, last activity, revoked at.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of logouts revoke the session and redirect to the initial screen.
- **SC-002**: 0 protected requests succeed with a revoked or expired session.

## Assumptions

- The global navigation menu is part of the application shell (cross-cutting section 7).
- HU-00 is the initial screen with the two accesses, delivered by HU-05.

## Revision Notes (v2)

- Logout now requires server-side revocation and covers session expiry.
- Declared the dependency on the application shell.

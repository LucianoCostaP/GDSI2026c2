# Feature Specification: Access Account Profile

**Feature Branch**: `hu-10-profile-access`  
**Created**: 2026-10-17  
**Status**: Draft  
**Backlog Reference**: HU-10 (Estimate: 2, Priority: Baja, MVP: Yes)  
**Shared rules**: [cross-cutting](../_shared/cross-cutting.md)  
**Input**: "As an authenticated user (Socio, Dirigente or Administrador), I want to access my profile from a visible button, so that I can consult my account information."

## User Scenarios & Testing

### User Story 1 - Open My Profile (Priority: P2)

As an authenticated user, I want to open the profile page for my account so that I can review the basic information associated with it.

**Why this priority**: Provides a consistent place to consult account details across all authenticated roles.

**Independent Test**: Sign in separately as a Socio, Dirigente, and Administrador; open “Mi Perfil” from the global navigation and confirm each sees their own role-appropriate account details. Confirm the route is unavailable after logout.

**Acceptance Scenarios**:

1. **Given** an authenticated user on any protected screen, **When** they open the global navigation, **Then** “Mi Perfil” is visible and accessible.
2. **Given** the user selects “Mi Perfil”, **When** the profile loads, **Then** the system shows the profile associated with the current account and role.
3. **Given** a Socio account, **When** its profile is shown, **Then** it displays the basic account information available for that account, including name and access identifier.
4. **Given** a management account, **When** its profile is shown, **Then** it displays the basic account information available for that account, including name, email/access identifier, and role.
5. **Given** no authenticated session or a revoked/expired session, **When** the user opens the profile route, **Then** access is denied and the user is sent to the appropriate sign-in entry point.
6. **Given** a profile is displayed, **When** the user attempts to edit account information, **Then** no profile changes are made; this story provides read-only access.

### Edge Cases

- A person with separate Socio and management accounts sees the profile for the account used to sign in; the profile does not combine identities.
- If a profile field is unavailable, the page omits it or labels it unavailable rather than presenting fabricated data.
- Role checks are enforced on the server; hiding navigation does not secure the route.

## Requirements

### Functional Requirements

- **FR-001**: System MUST show a “Mi Perfil” entry in authenticated global navigation for Socio, Dirigente, and Administrador.
- **FR-002**: System MUST show the profile belonging to the active account and role.
- **FR-003**: System MUST show the account's basic name and access identifier, plus role-appropriate available account details.
- **FR-004**: System MUST require a valid authenticated session to access the profile view.
- **FR-005**: System MUST keep the profile read-only in this story.

### Key Entities

- **ProfileView**: authenticated account, role, and the basic account fields permitted for display.

## Success Criteria

- **SC-001**: All three roles can reach their own profile from the global navigation.
- **SC-002**: No unauthenticated or expired session can retrieve a profile.
- **SC-003**: Profile access causes no account data to change.

## Assumptions

- “Basic information” means the account name and access identifier, plus the account role for management users. Additional role-specific fields must come from the account data already defined by HU-01, HU-05, HU-06, HU-07, and HU-08; this story does not add editable profile fields.

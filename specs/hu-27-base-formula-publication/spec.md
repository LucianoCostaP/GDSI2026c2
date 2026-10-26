# Feature Specification: Publish the Base Scoring Formula

**Feature Branch**: `hu-27-base-formula-publication`
**Created**: 2026-10-25 (v1) | **Revised**: 2026-10-26 (v2)
**Status**: Draft
**Backlog Reference**: HU-27 (Estimate: 2, Priority: Media, MVP: Yes). Re-estimate: formula catalog, preview, lock and per-club versioning. Although its priority is Media, it blocks HU-25 and HU-28 and must be built before them.
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As an Admin, I want to publish the base formula of the scoring system, with its variables and configurable weights, so that the weights can later be adjusted (HU-28) without changing the structure of the algorithm."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Publish the Base Scoring Formula (Priority: P2)

The product ships a **formula catalog** (cross-cutting section 7). The Admin of a club chooses one formula of the catalog, sets its initial parameter values, previews what the Socios will read about it (HU-13) and publishes it. The publication creates the **rules version** in force for that club.

**Why this priority**: Without a published base formula there are no rules in force for the club: HU-28 cannot adjust parameters, HU-25 cannot calculate a ranking and HU-13 has nothing to explain.

**Independent Test**: On a club with nothing published, verify HU-25 and HU-28 are blocked and a Socio of that club sees the "no rules yet" message (HU-13). As an Admin, open the catalog, choose a formula, set values within the limits, review the preview and publish. Verify that the preview of invalid values shows the violations and no explanation, that rules version 1 is in force for that club only, that HU-13 shows the explanation, that variables cannot be added or removed, and that after locking the formula (scenario 11) a new publication is rejected.

**Acceptance Scenarios**:

1. **Given** an Admin logged in, **When** they open the formula section, **Then** they see the catalog (name, version and description of each formula), which formula and rules version are in force for their club (if any), and whether the formula is locked.
2. **Given** a formula of the catalog, **When** the Admin opens it, **Then** they see its structure: variables, every parameter with its default and limits, the constants and derived values (read-only) and the constraints (for example the sum rule), with the parameters prefilled (defaults, or the values in force where scenario 8 applies).
3. **Given** the formula open, **When** the Admin sets the initial parameter values, **Then** they are validated against the limits and constraints of the formula using the same rules as HU-28; a violation is reported naming the parameter and its limits, or showing the sum that fails.
4. **Given** values that satisfy scenario 3 (every parameter present, within its limits and meeting the constraints), **When** the Admin asks for the preview, **Then** they see the explanation exactly as the Socios will read it (HU-13), rendered with the values entered. The preview is not saved and does not change the rules in force. **Given** values that do not satisfy scenario 3 (a missing parameter, a limit or a constraint violated), **When** the Admin asks for the preview, **Then** no explanation is shown, only the violations as in scenario 3; the system never completes missing parameters with defaults on its own.
5. **Given** valid values, **When** the Admin confirms the publication after a message stating that these values become the official rules of the club, **Then** the formula is published and a new rules version is in force immediately, with no extra approval step (version 1 if the club had none).
6. **Given** a published formula, **When** an Admin looks for ways to change its structure, **Then** none exist: only parameter values can change (HU-28), variables are never added or removed, and there is no screen to create a formula.
7. **Given** no published formula in the club, **When** an Admin tries to adjust parameters (HU-28) or calculate the ranking (HU-25), **Then** the action is blocked with the reason, and the Socios of the club see the "no rules yet" message in HU-13.
8. **Given** a rules version in force, **When** the Admin publishes a different formula of the catalog or a newer version of the same one, **Then** a new rules version starts from it, prefilled with the values in force for the parameters that exist in both with compatible limits and with the defaults for the rest. The ranking does not change until HU-25 runs and HU-13 shows its notice.
9. **Given** a rules version in force, **When** the Admin tries to publish the same formula at the same version, **Then** it is rejected: changing values of the formula in force is HU-28.
10. **Given** a publication, **When** it completes, **Then** the rules version is stored unchanged with its number, the formula and its version, who published, when and the values, and the publication is audited. There is no version history screen in the MVP. After publishing, the Admin sees the rules in force read-only and the explanation Socios see (HU-13); no edit control is offered until HU-28 exists.
11. **Given** an Admin, **When** they lock the formula giving a reason, **Then** while it is locked publishing a formula (HU-27) and adjusting parameters (HU-28) are rejected with a message saying that the formula is locked, since when, by whom and why. Any Admin of the club can unlock it, also giving a reason; the lock and the unlock are audited. The lock does not affect viewing, HU-25 or HU-13.
12. **Given** an Admin who opened the publication form, **When** the formula is locked or the rules in force changed in the meantime and they confirm, **Then** the publication is refused and they must reload.
13. **Given** a logged-in Socio, **When** they look for these actions, **Then** they are not available and the server rejects the request; without session the request is rejected as unauthenticated.
14. **Given** two clubs, **When** an Admin of one publishes, locks or reads rules, **Then** only the rules and lock of their own club are involved; the club comes from the Admin's account, never from a request parameter.

---

### Edge Cases

- **The catalog is code**: each formula is a descriptor shipped with the product (scoring model section 7) together with its calculation, which is pure and unique (constitution principle 1). Adding a formula to the catalog is a product release; the Admin cannot create a variable or a formula from the screen. A new variable only supported by a new calculation needs that calculation.
- **Descriptor validation**: the product's tests fail if a descriptor has a default outside its limits, an empty or inverted range, or an explanation placeholder that is not a parameter of the formula.
- **Lock without a published formula**: allowed; it prevents the first publication until unlocked. Locking an already locked formula, or unlocking an unlocked one, is rejected.
- **Season cut-off** (HU-28, 14 days before the season start) is independent from the lock and does not apply to the publication of HU-27. Changing parameters (HU-28) needs the formula unlocked **and** the cut-off not reached.
- **Decimal arithmetic**: limits, sums and values are compared as decimals, never as binary floating point.
- **Audit**: every publication and every lock or unlock records who, when, the reason (for locks) and the values.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST list the formulas of the catalog and show which one is in force for the club.
- **FR-002**: System MUST show the structure of a formula from its descriptor: variables, parameters, defaults, limits, constants, derived values and constraints.
- **FR-003**: System MUST validate the initial values with the same limits, constraints and code as HU-28, using decimal arithmetic.
- **FR-004**: System MUST offer a preview of the HU-13 explanation rendered with the values entered, only when they are valid and without saving anything; otherwise it MUST report the violations and show no explanation.
- **FR-005**: System MUST ask for confirmation, stating that the values become the official rules, and then create the new rules version in force atomically.
- **FR-006**: System MUST NOT allow adding or removing variables, or creating formulas, from the screen.
- **FR-007**: System MUST store every published rules version unchanged (version, formula and its version, author, date, values), because rankings and the notice of HU-13 refer to it, and audit the publication. A history view is outside the MVP.
- **FR-008**: System MUST block HU-25 and HU-28 for a club until a formula is published.
- **FR-009**: System MUST let an Admin lock and unlock the formula with a reason, and while it is locked MUST reject the publication (HU-27) and the adjustment of parameters (HU-28).
- **FR-010**: System MUST prevent concurrent overwrites (version check) and refuse a confirmation made over a stale state.
- **FR-011**: System MUST keep rules and lock separate per club and take the club from the authenticated account.
- **FR-012**: System MUST restrict these actions to Admins, enforced on the server, and audit them.

### Key Entities

- **FormulaDescriptor** (catalog entry, in code): id, name, version, description, variables, parameters (key, symbol, name, unit, default, limits), constants, derived values, constraints, explanation template (Spanish).
- **RulesVersion**: club, number, formula id and version, parameter values (decimal), in force since, published by, previous version, state `in force` or `superseded`. Shared with HU-28.
- **FormulaLock**: club, state (`unlocked` or `locked`), reason, changed by, changed at.

## Messages and codes *(pending)*

Texts and codes for these situations are defined while implementing and added here in the same PR (README, decision 40): formula not published (block), formula locked, limit violated, constraint violated (sum), confirmation statement, successful publication, stale state (reload), same formula already in force, lock and unlock confirmations, lock state conflicts, forbidden, unauthenticated.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 0 rankings are calculated for a club without a published formula.
- **SC-002**: 100% of publications and locks appear in the audit with author, date and values.
- **SC-003**: 0 publications or parameter changes are accepted while the formula is locked.
- **SC-004**: 0 publications are accepted with values outside the limits or breaking a constraint.
- **SC-005**: 0 requests read or change the rules of a club other than the one of the authenticated account.

## Assumptions

- The catalog of the MVP has one formula: the scoring model v1; more formulas arrive with product releases.
- Each Admin and each Socio belongs to one club (README, decision 34).
- This replaces the earlier bootstrap task "seed rules version 1": the catalog ships, and the Admin publishes.

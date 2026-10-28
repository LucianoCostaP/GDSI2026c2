# Feature Specification: View Explanation of How the Ranking Works

**Feature Branch**: `hu-13-ranking-explanation`
**Created**: 2026-10-11 | **Revised**: 2026-10-27 (v5)
**Status**: Draft
**Backlog Reference**: HU-13 (Estimate: 1, Priority: Media, MVP: Yes). Re-estimate: generated text, empty states and entry point.
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)
**Input**: "As a Socio of the club, I want to consult an explanation of how the ranking and scoring system works, so that I understand which criteria determine my priority for ticket purchase access."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Explanation of How the Ranking Works (Priority: P2)

As a Socio of the club, I want to consult an explanation of how the ranking and scoring system works, so that I understand which criteria determine my priority for ticket purchase access.

The explanation is **generated automatically** from the formula published by the club's Admin (HU-27) and the values in force. It has two blocks: a **formula block**, written from the explanation template of the formula in the catalog, and a **common block** with the rules every formula shares (scale, who appears, tiebreak).

**Why this priority**: Transparency about the rules builds trust in the ranking.

**Independent Test**: With nothing published, open the explanation as a Socio and see the "no rules yet" message. Publish a formula as Admin (HU-27), open it again and verify the explanation. Publish another version of the rules and verify the explanation shows the new values with no manual edit. The Admin's preview in HU-27 must show the same text.

**Acceptance Scenarios**:

1. **Given** a logged-in Socio and a published formula in their club, **When** they open the ranking explanation, **Then** a plain-language explanation in Spanish is shown: what the formula takes into account (each variable or pillar, how it affects the score and its **current weights and parameters**) and the 0–100 scale.
2. **Given** the explanation screen, **When** the Socio interacts with it, **Then** it is read-only.
3. **Given** the rules in force changed (HU-27 or HU-28), **When** the Socio opens the explanation, **Then** it reflects the rules currently in force and never describes rules that are no longer in force.
4. **Given** two Socios of the same club, **When** they open the section, **Then** both see the same explanation, with no personalization; a Socio of another club sees the explanation of their own club.
5. **Given** the rules in force differ from the rules used by the latest completed ranking, **When** the Socio opens the explanation, **Then** a notice says the ranking will reflect them after the next calculation.
6. **Given** a club with no published formula, **When** a Socio opens the section, **Then** a friendly message in Spanish says that the club has not published its scoring rules yet; it is not an error and no explanation is shown.
7. **Given** a club with rules in force but no completed ranking yet, **When** the Socio opens the section, **Then** the explanation is shown normally, without the notice of scenario 5.
8. **Given** the explanation, **When** it shows the common block, **Then** it states that only Socios with fees up to date appear, that their history is kept and that a Socio who pays up returns with their accumulated record, and that equal scores are ordered by seniority, then age, then document number, with no data of other Socios.
9. **Given** the explanation of the scoring model v1, **When** the formula block describes attendance, **Then** it states that matches of lower demand weigh more, and it covers the attendance window, distance, institutional participation with its 365-day validity, seniority and age, and the new-member bonus, each with the current values.
10. **Given** a logged-in Socio, **When** they look for the explanation, **Then** they find it from the top navigation bar and from a shortcut on their home screen. The Socio sees it whatever their fee status.
11. **Given** an Admin or a request without session, **When** they request the Socio's explanation, **Then** it is rejected (Admins use the preview in HU-27).

---

### Edge Cases

- **Rule changes**: the content MUST never describe rules that are no longer in force.
- **Club of the Socio**: the club comes from the authenticated account, never from a request parameter.
- **Tiebreak wording**: stated generally, without exposing other Socios' data.
- **Template errors**: a placeholder of the explanation template that is not a parameter of the formula is detected by the product's tests (HU-27, edge cases), never shown to a Socio.
- **Other formulas**: a new formula in the catalog brings its own template; this story does not change.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a section that explains in simple Spanish how the score is calculated.
- **FR-002**: System MUST present it as read-only.
- **FR-003**: System MUST generate the explanation from the formula and the rules version in force of the Socio's club (template plus values), so it cannot drift from the rules.
- **FR-004**: System MUST show the same explanation to every Socio of a club.
- **FR-005**: System MUST show the notice of scenario 5 when applicable and not show it when there is no completed ranking.
- **FR-006**: System MUST show the friendly "no rules yet" message when the club has no published formula.
- **FR-007**: System MUST include the common block (scale, eligibility and history, tiebreak) in every explanation.
- **FR-008**: System MUST use the same generation for the Admin's preview in HU-27 and for the Socio's view.
- **FR-009**: System MUST offer the entry points of scenario 10 and restrict the endpoint to Socios, enforced on the server.

### Key Entities

- **RankingExplanation**: the explanation template of the formula, the common block and the values of the rules version in force; generated, not stored.

## Messages and codes

Defined while implementing (README, decision 40). The texts are in Spanish and come from the server. The club reviews the copy.

| Situation | HTTP | Code | Message |
|---|---|---|---|
| No published formula in the club (scenario 6; not an error) | 200 | `status: "none"` | Todavía no hay reglas de puntaje publicadas. Cuando el club las publique, vas a poder verlas acá. |
| Rules in force differ from the latest completed ranking (scenario 5) | 200 | `notice.code = RULES_AHEAD_OF_RANKING` | Estas reglas se van a reflejar en el ranking después del próximo cálculo. |
| Explanation title (the front also uses it as the home shortcut label) | — | — | ¿Cómo se calcula mi puntaje? |
| Label in the top navigation bar | — | — | Cómo se calcula |
| Loading, front only | — | — | Cargando la explicación… |
| Load error, front only | — | — | No pudimos cargar la explicación. Probá de nuevo en un rato. |
| Socio account without club | 403 | `MEMBER_WITHOUT_CLUB` | The front shows: Tu cuenta no tiene un club asignado. Consultá con el club. |
| Forbidden (Admin) | 403 | `FORBIDDEN` | (existing code) |
| Unauthenticated | 401 | `NOT_AUTHENTICATED` | (existing code) |

The explanation texts (formula block per formula, common block) live in the formula descriptor and in `app/scoring/explanation.py`; they are reviewed together with the formula (scoring model, section 7). The numbers a template writes by hand (class factors, points per month, 365 days) are checked by a test against the constants of the descriptor.

### API

Under the Socio's session; the club comes from the account (decision 34). One route, no aliases, no `club_id` or `X-Club-ID` (if they arrive they are ignored).

- `GET /member/scoring/explanation` → 200 `{status, message, rules_version, formula, explanation, notice}`.
  - `status`: `published` or `none`. With `none`, `message` has the text above and `rules_version`, `formula`, `explanation` and `notice` are `null`.
  - `explanation`: the same object the Admin gets in HU-27 (`{title, blocks: [{id: "formula" | "common", sections: [{heading, paragraphs}]}]}`), built by the same function (FR-008).
  - `notice`: `null` or `{code, message}`. Without a completed ranking it is always `null` (scenario 7).
  - The response carries `Cache-Control: no-store`. It never includes who published the rules or the formula lock, and the lock does not affect it.
- Until HU-25 exists there is no completed ranking: `ranking_service.latest_completed_ranking_rules_number` answers `None`. HU-25 replaces it and adds the integration test of scenario 5.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of Socios of a club see the same explanation for the same rules version.
- **SC-002**: After every publication or rules change the explanation shows the new values with no manual edit.
- **SC-003**: The Admin's preview and the Socio's view are identical for the same values.

## Assumptions

- Decided: the text is generated automatically from the published formula; the Admin reviews it only through the preview of HU-27, with no separate approval step.
- All text is in Spanish (Argentina).
- Navigation labels are proposals, for example "¿Cómo se calcula mi puntaje?".

## Revision Notes

- v2: content defined by the scoring model and generated from the rules in force; added the notice for rules versus the latest ranking.
- v3: added the statement about fee status and kept history.
- v5: messages, codes and API defined with the implementation (decision 40); `MEMBER_WITHOUT_CLUB`; the response never exposes Admin data; `no-store`.
- v4: works with any formula of the catalog (formula block plus common block); added the empty states, the entry points, per-club rules and the preview shared with HU-27.

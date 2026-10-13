# Cross-Cutting Rules

Rules that apply to every spec. Individual specs reference this file instead of repeating it. Values marked **default** are system settings that can be changed without a new story.

## 1. Time zone

- All business rules and all displayed dates and times use **America/Argentina/Buenos_Aires**. Values are stored in UTC.
- This applies to the 24-hour publication window (HU-22), the season cut-off (HU-28), wave schedules (HU-37) and countdowns (HU-39).
- Countdowns are computed from the **server** clock, never the device clock.

## 2. Roles and permissions

| Capability | Socio | Dirigente | Administrador |
|---|---|---|---|
| Activate account by DNI / member number (HU-01) | Yes | No | No |
| Log in (HU-05 / HU-06) | HU-05 | HU-06 | HU-06 |
| Create / activate management accounts (HU-07 / HU-08) | No | No | Create: Yes. Activate: invitee |
| Load events, publish, attendance, participation (HU-21, 22, 24, N1) | No | No | Yes |
| Run ranking calculation (HU-25) | No | No | Yes |
| Segmentation and schedule (HU-36, HU-37) | No | No | Yes |
| Adjust scoring parameters (HU-28) | No | Yes | No |
| Simulate rules change (HU-29) | No | Yes | Yes |
| View ranking explanation, own score, breakdown, simulator (HU-13, 14, 16, 18) | Yes | No | No |
| View upcoming events, own slot (HU-17, HU-39) | Yes | No | No |
| Log out (HU-11) | Yes | Yes | Yes |

- Every protected action is authorized on the server by role. Hiding a button is not enough.
- A person who is both Socio and Dirigente has **separate accounts** per door. "Acceso Socio" never grants management access and "Acceso Dirigente/Administrador" never accepts DNI or member number.

## 3. Authentication parameters (defaults)

| Setting | Default |
|---|---|
| Access code | 6 digits, random, single use |
| Code expiry | 10 minutes |
| Failed attempts per code | 5, then the code is invalidated |
| Resend cooldown | 60 seconds; a new code invalidates the previous one |
| Lock after repeated failures | 15 minutes per identifier |
| Lookup rate limit (HU-01, HU-05, HU-06) | 10 requests/minute per IP and 5 per identifier per hour |
| Session | idle timeout 30 minutes, absolute 12 hours, server-side revocation on logout |
| Management invitation | single-use token, valid 72 hours |
| Code delivery target | 95% of emails delivered in under 30 seconds |

- Responses never include personal data other than what the user typed.
- Unknown identifiers in login (HU-05, HU-06) get a generic message that does not reveal whether the identifier exists.

## 4. State names (used identically in every spec)

| Entity | States |
|---|---|
| Event | `pending importance definition` → `published`; `historical` (past event loaded for scoring history, never published) |
| Socio account | `not activated`, `activated` |
| Management account | `pending activation`, `active` |
| Invitation | `valid`, `used`, `expired`, `replaced`, `revoked` |
| Ranking | `running`, `completed`, `failed` |

## 5. Scoring consistency rules

- Socio-facing views (HU-14, HU-16, HU-18) are anchored to the **rules version of the latest completed ranking** and show it.
- HU-13 explains the rules **in force**. If they differ from the rules of the latest ranking, it states that the ranking will reflect them after the next calculation.
- HU-29 compares against the latest completed ranking.

## 6. Non-functional requirements (defaults)

| Area | Target |
|---|---|
| Ranking calculation (HU-25) | completes in under 15 minutes for the expected volume N_max [NEEDS CLARIFICATION: N_max; HU-14 uses 5,000 as an example], without blocking other screens |
| Rules-change simulation (HU-29) | result in under 3 seconds (95th percentile) for N_max |
| Read-only Socio screens | response under 2 seconds (95th percentile) |
| Accessibility | WCAG 2.1 AA: high contrast, large touch targets, keyboard navigation, readable at 200% zoom |
| Audit | every change of events, rules, accounts, attendance loads and ranking runs records who, when and the previous and new values |
| Language | UI in Spanish (Argentina); specs in English |

## 7. Bootstrap (technical tasks, not stories)

- Seed the first Administrador account.
- Seed rules version 1 with the defaults in `scoring-model.md`.
- Seed settings: default event class, season start date, maximum number of waves, minimum wave step, synchronization staleness limit.
- Deliver the application shell with the global navigation menu that HU-11 relies on, and the Socio and management home screens.

## 8. Settings registry

| Setting | Default | Used by |
|---|---|---|
| Default event class when not defined in 24 h | Clase B | HU-22 |
| Season start date | none (must be configured) | HU-28 |
| Maximum number of waves | 10 | HU-36 |
| Minimum minutes between wave openings | 5 | HU-37 |
| Row error tolerance in file loads | 5% | HU-24, HU-N1 |
| Data staleness limit | 24 hours | HU-25, HU-36 |
| Code, session and invitation values | section 3 | HU-01, 05, 06, 07, 08, 11 |

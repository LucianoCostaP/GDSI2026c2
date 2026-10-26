# Cross-Cutting Rules

Rules that apply to every spec. Individual specs reference this file instead of repeating it. Values marked **default** are system settings that can be changed without a new story.

## 1. Time zone

- All business rules and all displayed dates and times use **America/Argentina/Buenos_Aires**. Values are stored in UTC.
- This applies to the 24-hour publication window (HU-22), the season cut-off (HU-28), wave schedules (HU-37) and countdowns (HU-39).
- Countdowns are computed from the **server** clock, never the device clock.

## 2. Roles and permissions

There are two roles: **Socio** (a club member) and **Admin** (manages the system). Earlier versions of these specs split management into Dirigente and Administrador; both are now the single Admin role, with the union of their permissions.

| Capability | Socio | Admin |
|---|---|---|
| Activate account by DNI / member number (HU-01) | Yes | No |
| Log in (HU-05 / HU-06) | HU-05 | HU-06 |
| View own profile (HU-10) | Yes | Yes |
| Create / activate Admin accounts (HU-07 / HU-08) | No | Create: Yes. Activate: invitee |
| Review events received from the club, discard, confirm historical events, publish (HU-21, 22) | No | Yes |
| Approve attendance replacements, upload CSV files, see load results (HU-24) | No | Yes |
| Review club updates, withdraw and restore events (HU-23, outside the MVP) | No | Yes |
| See the roster receptions from the club and their rejections (HU-43) | No | Yes |
| Publish a formula of the catalog as the base formula, lock and unlock it (HU-27) | No | Yes |
| Run ranking calculation (HU-25) | No | Yes |
| Segmentation and schedule (HU-36, HU-37) | No | Yes |
| Adjust scoring parameters (HU-28) | No | Yes |
| Simulate rules change and its equity analysis (HU-29, HU-30) | No | Yes |
| View ranking explanation, own score, breakdown, simulator (HU-13, 14, 16, 18) | Yes | No |
| View upcoming events, own slot (HU-17, HU-39) | Yes | No |
| Log out (HU-11) | Yes | Yes |

- Every protected action is authorized on the server by role. Hiding a button is not enough.
- Each Admin and each Socio belongs to **one club** (section 9).
- **The club** is not a user role: it is an integration client. With its Bearer token it can only send and query its own data through the integration API (data-contract section 5: HU-43, HU-21, HU-23, HU-24). It has no session and no screen.
- A person who is both Socio and Admin has **separate accounts** per door. "Socio access" never grants management access and "Admin access" never accepts DNI or member number.

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
| Management invitation | single-use token, valid 48 hours; after that a new invitation must be created |
| Code delivery target | 95% of emails delivered in under 30 seconds |
| Masked email | first character of the local part, `***`, then `@` and the full domain: `juan.perez@gmail.com` → `j***@gmail.com` (HU-05, HU-08) |
| Email delivery failure | the user sees the error `EMAIL_DELIVERY_FAILED`; an access code that could not be sent is discarded and a new one can be requested right away (the resend cooldown counts only codes actually sent); an invitation that could not be sent undoes the account creation (HU-07) |
| Club integration token | random, at least 128 bits, one per club, stored hashed, never logged; rotated by the team |

- Responses never include personal data other than what the user typed.
- Unknown identifiers in login (HU-05, HU-06) get a generic message that does not reveal whether the identifier exists.

## 4. State names (used identically in every spec)

| Entity | States |
|---|---|
| Event | `pending importance definition` → `published`; `historical` (past event sent for scoring history, never published; accepts attendance once its class or points are confirmed); `discarded` (pending event the Admin discards, for example because the club cancelled it). HU-23 (outside the MVP) adds `withdrawn` (published event that will not take place, restorable while its start has not passed); no MVP story uses it |
| Socio account | `not activated`, `activated` |
| Management account | `pending activation`, `active` |
| Invitation | `valid`, `used`, `expired`, `replaced` |
| Ranking | `running`, `completed`, `failed` |
| Rules version (HU-27, HU-28) | `in force`, `superseded` |
| Formula lock (HU-27) | `unlocked`, `locked` |
| Load received from the club (HU-43, HU-24) | `receiving` → `processing` → `successful` or `failed`; attendance loads for an event that already has attendance: `pending approval` → `successful` (the previous one becomes `replaced`) or `rejected` |
| Event change sent by the club (HU-23) | `pending review` → `approved`, `rejected` or `replaced` |

## 5. Scoring consistency rules

- Socio-facing views (HU-14, HU-16, HU-18) are anchored to the **rules version of the latest completed ranking** and show it.
- HU-13 explains the rules **in force**. If they differ from the rules of the latest completed ranking, it states that the ranking will reflect them after the next calculation; with no completed ranking there is no notice. With no published formula it shows a friendly "no rules yet" message. The Admin's preview in HU-27 renders the same explanation.
- HU-29 compares against the latest completed ranking.

## 6. Non-functional requirements (defaults)

| Area | Target |
|---|---|
| Ranking calculation (HU-25) | completes in under 15 minutes for up to 500,000 Socios, without blocking other screens |
| Initial roster reception (HU-43) | up to 500,000 Socios processed in under one hour; discrepancies below 0.1% |
| Rules-change simulation (HU-29) | result in under 3 seconds (95th percentile) up to 50,000 Socios and under 10 seconds up to 500,000 |
| Volume | up to 500,000 Socios, typically far fewer. Admin lists are paginated. Wave membership is derived from ranking positions, never copied per Socio |
| Read-only Socio screens | response under 2 seconds (95th percentile) |
| Accessibility | WCAG 2.1 AA: high contrast, large touch targets, keyboard navigation, readable at 200% zoom |
| Audit | every change of events, rules, formula publications and locks, accounts, loads received from the club, attendance loads and ranking runs records who (Admin, club or system), when and the previous and new values |
| Language | UI in Spanish (Argentina); specs in English |

## 7. Bootstrap (technical tasks, not stories)

- Seed the first Admin account, assigned to the club it manages (the club is chosen at startup, by its code, and is required).
- Issue the club's integration token (stored hashed) and hand it to the club through a secure channel.
- Ship the formula catalog (first entry: `scoring-model.md` with its defaults and its explanation template, see its section 7), ready for the Admin of each club to publish a formula and create its rules version 1 (HU-27). Nothing is seeded as a rules version.
- Seed settings: default event class, default institutional event points, season start date, wave percentile step, minimum wave step, minimum publication lead, roster staleness limit.
- Deliver the application shell with the global navigation menu that HU-11 relies on, and the Socio and management home screens.

## 8. Settings registry

| Setting | Default | Used by |
|---|---|---|
| Default class for Partido events when not defined in time | Clase B | HU-22 |
| Default points for institutional/amateur events when not defined in time | 20 | HU-22 |
| Season start date | none (must be configured) | HU-28 |
| Wave percentile step | 20 (waves at 20%, 40%, 60%, 80%, 100%); must divide 100 | HU-36 |
| Minimum publication lead | 48 hours before the event start | HU-21, HU-22 |
| Window to adjust class or points after a reprogramming | 24 hours | HU-23 (outside the MVP) |
| Minimum minutes between wave openings | 5 | HU-37 |
| Row error tolerance in CSV files uploaded by the Admin (records sent by the club have no tolerance: they are rejected one by one) | 5% | HU-24 |
| Data staleness limit (age of the latest successful roster load) | 24 hours | HU-43, HU-25, HU-36 |
| Formula lock of a club at creation | unlocked | HU-27, HU-28 |
| Code, session and invitation values | section 3 | HU-01, 05, 06, 07, 08, 11 |

## 9. Tenancy

- The system serves several clubs. **Rules (formula, rules versions, lock) belong to a club**, and so do the rankings calculated from them.
- Every Admin and every Socio belongs to one club. The club is taken from the authenticated account or from the club's integration token, **never from a request parameter** (query, body or header chosen by the caller); endpoints that take the club from the account ignore such parameters if they arrive.
- The account of an Admin stores its club. An Admin created by another Admin (HU-07) belongs to the club of who creates it, and an email already used by an account of another club cannot be invited. An Admin account without a club is rejected on every club-scoped action.
- A user can only read and change data of their own club; a request for another club's data is rejected.
- The specs keep the single-club wording; read "the club" as "the club of the user".

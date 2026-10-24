# Cross-Cutting Rules

Rules that apply to every spec. Individual specs reference this file instead of repeating it. Values marked **default** are system settings that can be changed without a new story.

## 1. Time zone

- All business rules and all displayed dates and times use **America/Argentina/Buenos_Aires**. Values are stored in UTC.
- This applies to the 24-hour publication window (HU-22), the season cut-off (HU-28), wave schedules (HU-37) and countdowns (HU-39).
- Countdowns are computed from the **server** clock, never the device clock.

## 2. Roles and permissions

There are two roles: **Member** (a club member) and **Admin** (manages the system). Earlier versions of these specs split management into Dirigente and Administrador; both are now the single Admin role, with the union of their permissions.

| Capability | Member | Admin |
|---|---|---|
| Activate account by DNI / member number (HU-01) | Yes | No |
| Log in (HU-05 / HU-06) | HU-05 | HU-06 |
| Create / activate Admin accounts (HU-07 / HU-08) | No | Create: Yes. Activate: invitee |
| Import events, publish, load attendance and activities (HU-21, 22, 24) | No | Yes |
| Refresh, reprogram, withdraw and restore events (HU-23) | No | Yes |
| Run club data synchronization on demand and see its status (HU-N2) | No | Yes |
| Run ranking calculation (HU-25) | No | Yes |
| Segmentation and schedule (HU-36, HU-37) | No | Yes |
| Adjust scoring parameters (HU-28) | No | Yes |
| Simulate rules change (HU-29) | No | Yes |
| View ranking explanation, own score, breakdown, simulator (HU-13, 14, 16, 18) | Yes | No |
| View upcoming events, own slot (HU-17, HU-39) | Yes | No |
| Log out (HU-11) | Yes | Yes |

- Every protected action is authorized on the server by role. Hiding a button is not enough.
- A person who is both Member and Admin has **separate accounts** per door. "Member access" never grants management access and "Admin access" never accepts DNI or member number.

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

- Responses never include personal data other than what the user typed.
- Unknown identifiers in login (HU-05, HU-06) get a generic message that does not reveal whether the identifier exists.

## 4. State names (used identically in every spec)

| Entity | States |
|---|---|
| Event | `pending importance definition` → `published`; `historical` (past event imported for scoring history, never published); `discarded` (pending event the club no longer lists); `withdrawn` (published event that will not take place, restorable while its start has not passed) |
| Member account | `not activated`, `activated` |
| Management account | `pending activation`, `active` |
| Invitation | `valid`, `used`, `expired`, `replaced` |
| Ranking | `running`, `completed`, `failed` |

## 5. Scoring consistency rules

- Member-facing views (HU-14, HU-16, HU-18) are anchored to the **rules version of the latest completed ranking** and show it.
- HU-13 explains the rules **in force**. If they differ from the rules of the latest ranking, it states that the ranking will reflect them after the next calculation.
- HU-29 compares against the latest completed ranking.

## 6. Non-functional requirements (defaults)

| Area | Target |
|---|---|
| Ranking calculation (HU-25) | completes in under 15 minutes for up to 500,000 Members, without blocking other screens |
| Rules-change simulation (HU-29) | result in under 3 seconds (95th percentile) up to 50,000 Members and under 10 seconds up to 500,000 |
| Volume | up to 500,000 Members, typically far fewer. Admin lists are paginated. Wave membership is derived from ranking positions, never copied per Member |
| Read-only Member screens | response under 2 seconds (95th percentile) |
| Accessibility | WCAG 2.1 AA: high contrast, large touch targets, keyboard navigation, readable at 200% zoom |
| Audit | every change of events, rules, accounts, attendance loads and ranking runs records who, when and the previous and new values |
| Language | UI in Spanish (Argentina); specs in English |

## 7. Bootstrap (technical tasks, not stories)

- Seed the first Admin account.
- Configure the credentials of the club API (HU-N2) as a secret.
- Seed rules version 1 with the defaults in `scoring-model.md`.
- Seed settings: default event class, default institutional event points, season start date, wave percentile step, minimum wave step, minimum publication lead, synchronization staleness limit.
- Deliver the application shell with the global navigation menu that HU-11 relies on, and the Member and management home screens.

## 8. Settings registry

| Setting | Default | Used by |
|---|---|---|
| Default class for Partido events when not defined in time | Clase B | HU-22 |
| Default points for institutional/amateur events when not defined in time | 20 | HU-22 |
| Season start date | none (must be configured) | HU-28 |
| Wave percentile step | 20 (waves at 20%, 40%, 60%, 80%, 100%); must divide 100 | HU-36 |
| Minimum publication lead | 48 hours before the event start | HU-21, HU-22 |
| Window to adjust class or points after a reprogramming | 24 hours | HU-23 |
| Minimum minutes between wave openings | 5 | HU-37 |
| Row error tolerance in file loads | 5% | HU-24 |
| Data staleness limit | 24 hours | HU-25, HU-36 |
| Code, session and invitation values | section 3 | HU-01, 05, 06, 07, 08, 11 |

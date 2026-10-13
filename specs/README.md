# MVP Specs Index (v2)

20 specs for the MVP user stories plus 2 new stories required by the scoring model, and 3 shared documents. Backlog estimates are kept; stories whose scope grew are flagged for re-estimation.

## Shared documents

| Document | Purpose |
|---|---|
| [Scoring model v1](_shared/scoring-model.md) | The base formula, parameters with defaults and limits, calculation rules, worked example |
| [Data contract](_shared/data-contract.md) | Socio, event, attendance and participation data and file formats |
| [Cross-cutting rules](_shared/cross-cutting.md) | Time zone, permissions matrix, authentication parameters, state names, non-functional targets, bootstrap tasks, settings |

## Stories

| HU | Spec | Est. | Priority | Re-estimate |
|----|------|------|----------|-------------|
| HU-01 | [Identity Verification and Activation](hu-01-identity-verification/spec.md) | 3 | Alta | Yes (email-code step added) |
| HU-05 | [Socio Login and Initial Screen](hu-05-socio-login/spec.md) | 1 | Alta | Yes (initial screen, code and session base) |
| HU-06 | [Dirigente / Administrador Login](hu-06-dirigente-admin-login/spec.md) | 1 | Alta | |
| HU-07 | [Create Management Account](hu-07-management-account-creation/spec.md) | 3 | Alta | |
| HU-08 | [Activate Management Account](hu-08-management-account-activation/spec.md) | 2 | Media | Consider priority Alta |
| HU-11 | [Logout](hu-11-logout/spec.md) | 1 | Alta | Yes (needs the navigation shell) |
| HU-13 | [Ranking Explanation](hu-13-ranking-explanation/spec.md) | 1 | Media | |
| HU-14 | [Current Score and Position](hu-14-current-score-and-position/spec.md) | 3 | Alta | |
| HU-16 | [Score Breakdown](hu-16-score-breakdown/spec.md) | 3 | Media | |
| HU-17 | [Upcoming Events](hu-17-upcoming-events/spec.md) | 3 | Alta | |
| HU-18 | [Attendance Score Simulator](hu-18-attendance-score-simulator/spec.md) | 8 | Media | |
| HU-21 | [Event Base Information](hu-21-event-base-information/spec.md) | 3 | Alta | Yes (capacity, historical load, edit while pending) |
| HU-22 | [Event Class and Publication](hu-22-event-importance-and-publication/spec.md) | 5 | Alta | |
| HU-24 | [Attendance by File](hu-24-attendance-file-upload/spec.md) | 5 | Alta | |
| HU-25 | [Ranking Calculation](hu-25-ranking-calculation/spec.md) | 8 | Alta | Yes (full model and snapshot) |
| HU-28 | [Adjust Scoring Parameters](hu-28-scoring-weights-adjustment/spec.md) | 5 | Media | Yes (11 parameters) |
| HU-29 | [Rules Change Simulation](hu-29-rules-change-impact-simulation/spec.md) | 8 | Media | |
| HU-36 | [Wave Segmentation](hu-36-wave-segmentation/spec.md) | 8 | Alta | |
| HU-37 | [Wave Schedule](hu-37-wave-schedule-generation/spec.md) | 3 | Alta | |
| HU-39 | [Own Slot](hu-39-own-reservation-slot/spec.md) | 2 | Alta | |
| HU-N1 | [Institutional Participation Load](hu-n1-institutional-participation-load/spec.md) (new) | TBD | Alta | New |
| HU-N2 | [Club Data Sync](hu-n2-club-data-sync/spec.md) (new) | TBD | Alta | New |

## Decisions adopted

1. The base formula is the Scoring Model v1 and is complete.
2. The total score is capped at 100 after adding the new-member bonus; a "cap adjustment" component keeps the breakdown equal to the total.
3. `dsat` is the **inflection point** of the Gompertz curve (36.8% at `dsat`, about 95% at 1.68 × `dsat`). The "ceiling for 95–100%" wording in the parameter matrix must be corrected.
4. The parameters editable by the Dirigente are the ones in the parameter matrix (pillar weights, αA, dsat, Pinst_max, αT, Tref, Eref, γ, Bmax, Tmax, tcarencia). Event class factors and institutional point values are constants.
5. The institutional participation pillar is in the MVP, which adds HU-N1.

## Defaults set by this revision (change them in one place)

Event importance = class A/B/C with default class B; ranking population = Socios with fees up to date; attendance window = previous calendar year plus current year to date; rounding to two decimals; wave count rule with a maximum of 10; code, session and invitation parameters; time zone Buenos Aires; row-error tolerance of 5%; 24-hour minimum lead time for upcoming events; revoke of pending invitations.

## Open questions ([NEEDS CLARIFICATION] markers: 16 in the files, grouped here in 14 questions)

1. Confirm the proposed limits of each parameter (scoring model, section 4).
2. Is the "next verification step" in HU-01 the email code?
3. Do overdue fees block login (HU-05)? Current default: no.
4. Confirm the ranking population (fees up to date).
5. Confirm that the ranking takes effect at completion, with no separate confirm step (HU-25).
6. Confirm the wave count rule and the maximum number of waves (HU-36).
7. Confirm the event type catalog and the 24-hour minimum lead time (HU-21).
8. Confirm the attendance file format and the 5% tolerance (HU-24, HU-N1).
9. Should HU-18 also project the new position?
10. Events held at venues other than the club stadium (distance model).
11. Mode of the club data source: API or snapshot file (HU-N2).
12. Expected maximum number of Socios (N_max) for the performance targets.
13. Revoking a pending invitation (HU-07), not in the backlog.
14. Format of institutional participation exports (HU-N1).

## Backlog and plan changes required

- Add HU-N1 and HU-N2 to the backlog and the plan.
- Rename "importance" in the backlog language to "category (class A/B/C)", and state that a higher factor means lower demand.
- Remove from HU-36 and HU-39 the criteria about Abonados and transferred seats (the role no longer exists).
- Add the bootstrap tasks of cross-cutting section 7 to the plan.
- Correct the parameter matrix text for `dsat`.

## Residual risks

- Published events cannot be corrected in the MVP (HU-23 is out). Consider a minimal version.
- The wave schedule is informative: with no reservation, ticket-office export or notifications in the MVP, nothing enforces it. State this clearly in the demo.
- Using age as a score component is a policy choice the club should be able to defend before its Socios.

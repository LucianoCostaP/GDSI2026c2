# MVP Specs Index (v3)

22 specs: the 20 MVP stories, HU-23 in a minimal version, and 1 new story required by the scoring model (HU-N2), plus 3 shared documents. Backlog estimates are kept; stories whose scope grew are flagged for re-estimation. v3 applies the product owner's answers to the open questions.

## Shared documents

| Document | Purpose |
|---|---|
| [Scoring model v1](_shared/scoring-model.md) | The base formula, parameters with defaults and confirmed limits, calculation rules, worked example |
| [Data contract](_shared/data-contract.md) | Socio, event, attendance and participation data and formats |
| [Cross-cutting rules](_shared/cross-cutting.md) | Time zone, permissions matrix, authentication parameters, state names, non-functional targets, bootstrap tasks, settings |

## Stories

| HU | Spec | Est. | Priority | Re-estimate |
|----|------|------|----------|-------------|
| HU-01 | [Identity Verification and Activation](hu-01-identity-verification/spec.md) | 3 | Alta | Yes (email-code step) |
| HU-05 | [Socio Login and Initial Screen](hu-05-socio-login/spec.md) | 1 | Alta | Yes (initial screen, code and session base) |
| HU-06 | [Dirigente / Administrador Login](hu-06-dirigente-admin-login/spec.md) | 1 | Alta | |
| HU-07 | [Create Management Account](hu-07-management-account-creation/spec.md) | 3 | Alta | |
| HU-08 | [Activate Management Account](hu-08-management-account-activation/spec.md) | 2 | Media | Consider priority Alta |
| HU-11 | [Logout](hu-11-logout/spec.md) | 1 | Alta | Yes (needs the navigation shell) |
| HU-13 | [Ranking Explanation](hu-13-ranking-explanation/spec.md) | 1 | Media | |
| HU-14 | [Current Score and Position](hu-14-current-score-and-position/spec.md) | 3 | Alta | |
| HU-16 | [Score Breakdown](hu-16-score-breakdown/spec.md) | 3 | Media | |
| HU-17 | [Upcoming Events](hu-17-upcoming-events/spec.md) | 3 | Alta | |
| HU-18 | [Attendance Score Simulator](hu-18-attendance-score-simulator/spec.md) | 8 | Media | Yes (two event types, estimated position) |
| HU-21 | [Receive Event Base Information from the Club](hu-21-event-base-information/spec.md) | 3 | Alta | Yes (club push API, updates, discard, historical import) |
| HU-22 | [Event Class and Publication](hu-22-event-importance-and-publication/spec.md) | 5 | Alta | |
| HU-23 | [Event Reprogramming and Withdrawal](hu-23-event-reprogramming/spec.md) (minimal version, proposed for the MVP) | 5 in backlog; review | Alta (proposed) | New in the MVP |
| HU-24 | [Attendance and Recurring Activities from the Club](hu-24-attendance-load/spec.md) | 5 | Alta | Yes (club push API, activities, file fallback) |
| HU-25 | [Ranking Calculation](hu-25-ranking-calculation/spec.md) | 8 | Alta | Yes (full model, two event types, 500,000 Socios) |
| HU-28 | [Adjust Scoring Parameters](hu-28-scoring-weights-adjustment/spec.md) | 5 | Media | Yes (11 parameters) |
| HU-29 | [Rules Change Simulation](hu-29-rules-change-impact-simulation/spec.md) | 8 | Media | |
| HU-36 | [Wave Segmentation](hu-36-wave-segmentation/spec.md) | 8 | Alta | Probably lower (fixed percentile bands) |
| HU-37 | [Wave Schedule](hu-37-wave-schedule-generation/spec.md) | 3 | Alta | |
| HU-39 | [Own Slot](hu-39-own-reservation-slot/spec.md) | 2 | Alta | |
| HU-N2 | [Club Data Sync (API)](hu-n2-club-data-sync/spec.md) (new) | TBD | Alta | New |

## Decisions adopted

1. The base formula is the Scoring Model v1 and is complete. The total is capped at 100 after the new-member bonus; a "cap adjustment" component keeps the breakdown equal to the total.
2. `dsat` is the **inflection point** of the Gompertz curve (36.8% at `dsat`, about 95% at 1.68 × `dsat`).
3. The parameters editable by the Dirigente are the ones in the parameter matrix, with the proposed limits, now confirmed.
4. The institutional participation pillar is in the MVP.
5. Activation of a Socio finishes with the code sent by email (HU-01).
6. Overdue fees do not block login.
7. Only Socios with fees up to date appear in the ranking. Their history is kept, and a Socio who pays up returns with their accumulated record.
8. The ranking takes effect when the calculation completes, with no separate confirm step.
9. **Waves are percentile bands** in steps of 20: 20%, 40%, 60%, 80%, 100% (wave 1 is the best ranked). Capacity is not used.
10. **Two event types**: Partido (attendance pillar, needs a class, has waves) and Evento institucional/amateur (institutional pillar, no class, no waves). Elections and assemblies are institutional events. Events held outside the stadium are institutional/amateur.
11. **Minimum publication lead: 48 hours** before the event start. Automatic publication happens at the earlier of 24 hours after loading and 48 hours before the start.
12. The club **pushes attendance** to platform-provided endpoints in HU-24, like the Socio data of HU-N2. A CSV file with the same data is the fallback (`dni`, optional `numero_socio` and `fecha_evento`).
13. The attendance simulator (HU-18) shows an estimated position, clearly labeled as an estimate that holds the other Socios constant.
14. The club pushes its data to **platform-provided APIs** (HU-N2); the platform does not pull from club APIs.
15. Maximum volume: **500,000 Socios** (typically far fewer).
16. Management invitations expire after **48 hours** and must then be created again. There is no manual revocation.
17. **The points of an institutional event are defined by whoever publishes it** (a whole number from 1 to 100), elections and assemblies included, and are fixed once published.
18. **Recurring activities** (federated sport, subcommissions) are pushed by the club in HU-24 together with event attendance, with a file fallback and one shared validation mechanism. They are the only participation records; elections and assemblies are events. The club pushes Socio data in HU-N2.
19. **Events are pushed by the club** (HU-21): the club organizes them. The Administrador adjusts only the class of a Partido or the points of an institutional event when publishing (HU-22). The club event reference identifies the event for attendance submissions (HU-24).
20. **A minimal HU-23 enters the MVP**: the club pushes event rescheduling updates to the platform API (the club is the source of truth), with a 24-hour window to adjust class or points, plus the withdrawal (and restoration) of a published event that will not take place. Email notifications stay out.
21. Confirmed readings: wave 1 is the best 20% of the ranking; the 48-hour lead is the minimum time between publication and the event start; without revocation a mistyped invitation email stays valid up to 48 hours (double entry is the mitigation).

## Defaults set by this revision (change them in one place)

Default class B for Partidos not classified in time and 20 default points for institutional events without points when the automatic publication runs; row-error tolerance of 5%; code, session and lockout parameters; time zone Buenos Aires; attendance window of previous calendar year plus current year to date; rounding to two decimals; minimum 5 minutes between wave openings; HU-29 target of under 3 seconds up to 50,000 Socios and under 10 seconds up to 500,000.

## Open items

- Confirm the proposed historical event import route/payload and cancellation endpoint/payload with the club (event contract; absent from the referenced PDF).
- Agree Socio roster enum/nullability details, maximum chunk size, delta watermarks, and the operational channel for an Administrator-requested resync (Socios API contract).
- Confirm the published-match rescheduling rule with stakeholders: HU-23 permits changes inside 48 hours, while the PDF requires the new match date to remain at least 48 hours ahead.

## Interpretations to confirm (not blocking)

- Attendance at elections and assemblies is loaded like any other event attendance (HU-24).
- When nobody defines the points of an institutional event before the automatic publication, a default applies (a system setting, proposed 20).
- The points of an institutional event are limited to a whole number from 1 to 100, matching the maximum of the participation cap.
- The performance targets for 500,000 Socios (HU-25 under 15 minutes, HU-29 under 10 seconds) are proposals to validate with a load test.
- The club can push paginated full and incremental roster data to the platform API, and the target for the first full load (under one hour) depends on it.

## Backlog and plan changes required

- Add HU-N2 to the backlog and the plan, before HU-25.
- Extend HU-24 in the backlog to cover club pushes to platform-provided endpoints and recurring activities.
- Rename "importance" in the backlog language to "category (class A/B/C)" for Partidos, and state that a higher factor means lower demand.
- Change HU-23 in the backlog from "Quizás" to "SI", describe club-pushed event updates with the 24-hour review window, and add the withdrawal and restoration of an event.
- Rewrite HU-21 in the backlog as receipt of club-pushed data through platform-provided endpoints (read-only club data, updates, discard, historical import). Add the 48-hour publication lead and the points of institutional events to HU-22.
- Remove capacity from the language of HU-36 and describe the percentile waves.
- Remove from HU-36 and HU-39 the criteria about Abonados and transferred seats (the role no longer exists).
- Correct the parameter matrix text for `dsat` ("ceiling for 95-100%" is wrong: it is the inflection point).
- Add the bootstrap tasks of cross-cutting section 7 to the plan.

## Residual risks

- Socios are not notified by email when an event is rescheduled (HU-19/20 are out): they see the change only when they open the app.
- The wave schedule is informative: with no reservation, ticket-office export or notifications in the MVP, nothing enforces it. State this clearly in the demo.
- Using age as a score component is a policy choice the club should be able to defend before its Socios.
- The quality and timeliness of club pushes determine the freshness of the ranking.

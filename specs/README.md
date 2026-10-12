# MVP Specs Index

20 specs, one per backlog user story marked `MVP = SI`. Total estimate: 76.

| HU | Spec | Est. | Priority |
|----|------|------|----------|
| HU-01 | [Identity Verification by DNI / Member Number](hu-01-identity-verification/spec.md) | 3 | Alta |
| HU-05 | [Socio Login with Emailed Access Code](hu-05-socio-login/spec.md) | 1 | Alta |
| HU-06 | [Dirigente / Administrador Login with Emailed Access Code](hu-06-dirigente-admin-login/spec.md) | 1 | Alta |
| HU-07 | [Create Dirigente / Administrador Account](hu-07-management-account-creation/spec.md) | 3 | Alta |
| HU-08 | [Activate Dirigente / Administrador Account via Invitation](hu-08-management-account-activation/spec.md) | 2 | Media |
| HU-11 | [Logout](hu-11-logout/spec.md) | 1 | Alta |
| HU-13 | [View Explanation of How the Ranking Works](hu-13-ranking-explanation/spec.md) | 1 | Media |
| HU-14 | [View Current Score and Ranking Position](hu-14-current-score-and-position/spec.md) | 3 | Alta |
| HU-16 | [Score Components Breakdown](hu-16-score-breakdown/spec.md) | 3 | Media |
| HU-17 | [View Upcoming Events](hu-17-upcoming-events/spec.md) | 3 | Alta |
| HU-18 | [Estimated Score Simulator by Attendance](hu-18-attendance-score-simulator/spec.md) | 8 | Media |
| HU-21 | [Load Event Base Information](hu-21-event-base-information/spec.md) | 3 | Alta |
| HU-22 | [Define Event Importance and Publish](hu-22-event-importance-and-publication/spec.md) | 5 | Alta |
| HU-24 | [Load Attendance by File](hu-24-attendance-file-upload/spec.md) | 5 | Alta |
| HU-25 | [Run Ranking Calculation](hu-25-ranking-calculation/spec.md) | 8 | Alta |
| HU-28 | [Adjust Scoring Weights](hu-28-scoring-weights-adjustment/spec.md) | 5 | Media |
| HU-29 | [Simulate Impact of a Rules Change](hu-29-rules-change-impact-simulation/spec.md) | 8 | Media |
| HU-36 | [Segment Socios into Waves](hu-36-wave-segmentation/spec.md) | 8 | Alta |
| HU-37 | [Automatic Wave Schedule Generation](hu-37-wave-schedule-generation/spec.md) | 3 | Alta |
| HU-39 | [View Own Assigned Slot](hu-39-own-reservation-slot/spec.md) | 2 | Alta |

## Glossary
- **Socio**: club member. **Dirigente**: club leader who tunes scoring weights. **Administrador**: system administrator.
- **Oleada**: wave, a ranking percentile band that gets reservation access at a staggered time.

## Open questions / backlog gaps
1. **Socio activation is incomplete**: HU-01 advances to a "next verification step", and HU-05 redirects to an "activation flow", but no MVP story defines that step or completes the Socio account activation.
2. **Event capacity is never captured**: HU-36 needs real capacity (entries/seats), but HU-21/HU-22 only capture date, time, venue and type.
3. **Dependencies on non-MVP stories**: HU-22 (email on publish via HU-19; post-publication importance change via HU-23), HU-28 (base formula from HU-27), HU-36/39 (Abonado exclusion and seat transfer via HU-32/33, role "no longer exists"). Specs keep these as assumptions, not requirements.
4. **Undefined values**: code and invitation expiry, default event importance, attendance file format, number-of-waves rule, season start date source, and whether HU-25 needs a separate "confirm" step.
5. **HU-00** (initial screen) is referenced by HU-11 but has no story; it is covered inside HU-05.

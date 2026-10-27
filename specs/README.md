# MVP Specs Index (v4.2)

25 specs: the 24 stories the backlog marks as MVP, plus HU-23 (outside the MVP, kept as a ready spec), and 3 shared documents. Titles, estimates, priorities and MVP scope follow the backlog (`Backlog - US.csv`). v4 aligns the specs with the backlog and with the integration prototypes: **the club sends its data to an API the system exposes; the system never calls the club.** v4.1 applies the review in `CORRECCIONES_SPECS.txt` (decisions 24–33 and the table at the end). v4.2 reworks HU-27 and HU-13 around a formula catalog and per-club rules (decisions 34–40).

## Shared documents

| Document | Purpose |
|---|---|
| [Scoring model v1](_shared/scoring-model.md) | The base formula, parameters with defaults and confirmed limits, calculation rules, worked example |
| [Data contract](_shared/data-contract.md) | Socio, event, attendance and activity data, and the integration API the club calls |
| [Cross-cutting rules](_shared/cross-cutting.md) | Time zone, permissions matrix, authentication parameters, state names, non-functional targets, bootstrap tasks, settings |

## Stories

| HU | Spec | Est. | Priority | MVP |
|----|------|------|----------|-----|
| HU-01 | [Identity Verification and Activation](hu-01-identity-verification/spec.md) | 3 | Alta | Yes |
| HU-05 | [Socio Login and Initial Screen](hu-05-socio-login/spec.md) | 1 | Alta | Yes |
| HU-06 | [Admin Login](hu-06-dirigente-admin-login/spec.md) | 3 | Alta | Yes |
| HU-07 | [Create Admin Account](hu-07-management-account-creation/spec.md) | 3 | Alta | Yes |
| HU-08 | [Activate Admin Account via Invitation](hu-08-management-account-activation/spec.md) | 2 | Media | Yes |
| HU-10 | [Access the Profile](hu-10-profile/spec.md) | 2 | Baja | Yes |
| HU-11 | [Logout](hu-11-logout/spec.md) | 1 | Alta | Yes |
| HU-13 | [Ranking Explanation](hu-13-ranking-explanation/spec.md) | 1 | Media | Yes |
| HU-14 | [Current Score and Position](hu-14-current-score-and-position/spec.md) | 3 | Alta | Yes |
| HU-16 | [Score Breakdown](hu-16-score-breakdown/spec.md) | 3 | Media | Yes |
| HU-17 | [Upcoming Events](hu-17-upcoming-events/spec.md) | 3 | Alta | Yes |
| HU-18 | [Attendance Score Simulator](hu-18-attendance-score-simulator/spec.md) | 8 | Media | Yes |
| HU-21 | [Receive Events Sent by the Club](hu-21-club-event-reception/spec.md) | 5 | Alta | Yes |
| HU-22 | [Define Event Category (Class A/B/C) or Points and Publish](hu-22-event-class-and-publication/spec.md) | 5 | Alta | Yes |
| HU-23 | [Event Reprogramming, Withdrawal and Restoration](hu-23-event-reprogramming/spec.md) | 5 | Media | **No** |
| HU-24 | [Load Attendance and Recurring Activities from the Club](hu-24-attendance-load/spec.md) | 5 | Alta | Yes |
| HU-25 | [Ranking Calculation](hu-25-ranking-calculation/spec.md) | 8 | Alta | Yes |
| HU-27 | [Publish the Base Scoring Formula](hu-27-base-formula-publication/spec.md) | 2 | Media | Yes |
| HU-28 | [Adjust Scoring Parameters](hu-28-scoring-weights-adjustment/spec.md) | 5 | Media | Yes |
| HU-29 | [Rules Change Simulation](hu-29-rules-change-impact-simulation/spec.md) | 8 | Media | Yes |
| HU-30 | [Equity Analysis of a Rules Simulation](hu-30-equity-analysis/spec.md) | 5 | Media | Yes |
| HU-36 | [Wave Segmentation](hu-36-wave-segmentation/spec.md) | 8 | Alta | Yes |
| HU-37 | [Wave Schedule](hu-37-wave-schedule-generation/spec.md) | 3 | Alta | Yes |
| HU-39 | [Own Slot](hu-39-own-reservation-slot/spec.md) | 2 | Alta | Yes |
| HU-43 | [Receive and Update the Socio Roster Sent by the Club](hu-43-club-roster-reception/spec.md) | 8 | Alta | Yes |

## Decisions adopted

1. The base formula is the Scoring Model v1 and is complete. The total is capped at 100 after the new-member bonus; a "cap adjustment" component keeps the breakdown equal to the total. The Admin publishes a formula of the catalog as the base formula (HU-27) and then adjusts its parameters (HU-28).
2. `dsat` is the **inflection point** of the Gompertz curve (36.8% at `dsat`, about 95% at 1.68 × `dsat`).
3. The parameters editable by the Admin are the ones in the parameter matrix, with the proposed limits, now confirmed.
4. The institutional participation pillar is in the MVP.
5. Activation of a Socio finishes with the code sent by email (HU-01).
6. Overdue fees do not block login.
7. Only Socios with fees up to date appear in the ranking. Their history is kept, and a Socio who pays up returns with their accumulated record.
8. The ranking takes effect when the calculation completes, with no separate confirm step.
9. **Waves are percentile bands** in steps of 20: 20%, 40%, 60%, 80%, 100% (wave 1 is the best ranked). Capacity is not used.
10. **Two event types**: Partido (attendance pillar, needs a class, has waves) and Evento institucional/amateur (institutional pillar, no class, no waves). Elections and assemblies are institutional events. Events held outside the stadium are institutional/amateur.
11. **Minimum publication lead: 48 hours** before the event start. Automatic publication happens at the earlier of 24 hours after the event is received and 48 hours before the start.
12. **The club sends, the system receives.** The Socio roster (HU-43), events (HU-21), attendance and recurring activities (HU-24) arrive through an integration API the system exposes, authenticated with a Bearer token per club. The system never calls an API of the club (data contract, section 5).
13. The attendance simulator (HU-18) shows an estimated position, clearly labeled as an estimate that holds the other Socios constant.
14. **Records sent by the club are validated one by one**: invalid records are rejected with a code and a reason, valid ones are applied, as the HU-43 prototype does. A structurally invalid request is rejected whole. Resends are idempotent.
15. Maximum volume: **500,000 Socios** (typically far fewer).
16. Admin invitations expire after **48 hours** and must then be created again. There is no manual revocation.
17. **The points of an institutional event are defined by whoever publishes it** (a whole number from 1 to 100), elections and assemblies included, and are fixed once published.
18. **Recurring activities** (federated sport, subcommissions) arrive in HU-24 together with event attendance, with a CSV fallback uploaded by the Admin. They are the only participation records; elections and assemblies are events.
19. **The club organizes the events** (HU-21). The Admin adjusts only the class of a Partido or the points of an institutional event when publishing (HU-22). The event's `id_externo` identifies it when the club sends its attendance (HU-24).
20. **HU-23 is outside the MVP** (backlog). In the MVP, a pending event resent by the club is updated, and a published one is omitted. With HU-23, an update of a published event waits for the Admin's approval, and published events can be withdrawn and restored.
21. Confirmed readings: wave 1 is the best 20% of the ranking; the 48-hour lead is the minimum time between publication and the event start; without revocation a mistyped invitation email stays valid up to 48 hours (double entry is the mitigation).
22. **Two roles: Socio and Admin.** Dirigente and Administrador are merged into a single Admin role with the union of their permissions (cross-cutting section 2). The club is an integration client, not a role.
23. **A second attendance load for the same event waits for the Admin's approval** (HU-24). The 5% row-error tolerance applies only to CSV files uploaded by the Admin.

24. **User-facing messages have an exact text and an error code**, so tests compare the text. HU-01: `MEMBER_NOT_FOUND` "No encontramos ese DNI o N° de socio." (and the other three cases); HU-17: "No hay eventos próximos publicados.".
25. **Masked email format**: first character of the local part, `***`, `@` and the full domain (`j***@gmail.com`), as the code already does (cross-cutting section 3).
26. **An upcoming event with less than 48 hours of lead is rejected, never registered** (`422 INSUFFICIENT_LEAD`), and the rejection is shown in the Admin's reception log (HU-21). The "registered as non-publishable" alternative is dropped.
27. **Size limits**: CSV files up to 10 MB and 100,000 rows; club requests up to 10,000 records per page or batch and 10 MB; up to 100,000 attendance records per event (data contract, section 5).
28. **"Critically interrupted" load**: a paged load (roster full load, attendance) that does not receive all its pages within 60 minutes of the first one ends `failed` (`LOAD_EXPIRED`) and applies nothing (HU-43, HU-24).
29. **"Reliable" incremental batch**: accepted only if a successful full load exists and its `desde` is not later than the `hasta` of the last successful batch of the same kind; otherwise it is rejected whole (`WATERMARK_GAP`) (HU-43, HU-24).
30. **Email delivery failure** (HU-01, 05, 06): the error `EMAIL_DELIVERY_FAILED` is shown, the unsent code is discarded and a new one can be requested right away: the 60-second cooldown counts only codes that were actually sent, as the code already does. **HU-07**: a failed invitation email undoes the whole creation, so the Admin is never left with a pending account for 48 hours; there is no resend of a sent invitation.
31. **Baja of a Socio with an account** (HU-43): the Socio can no longer activate or log in (treated as not found / generic message), and their open sessions are revoked when the baja is applied. A new alta restores access and history.
32. **Started events leave the upcoming list for both types** (HU-17); no event stays visible until the end of its day.
33. **No MVP spec depends on HU-23**: the state `withdrawn` and the effects of withdrawals and reprogramming on HU-17, HU-22, HU-36, HU-37 and HU-39 live only in HU-23 (outside the MVP). The constitution (DoR, DoD, thresholds, branches, commits, protection of `main`) is versioned in `docs/constitution.md`.

34. **Rules are per club; tenancy is closed.** The system serves several clubs; each Admin and each Socio belongs to one club; the formula, rules versions, lock and rankings belong to the club. The club comes from the account or token, never from a request parameter (cross-cutting section 9).
35. **Formula catalog.** The product ships a catalog of formulas (descriptor plus pure calculation); the Admin of a club publishes one of them with initial values (HU-27). More formulas are added with product releases, never from a screen (scoring model, section 7).
36. **The explanation is generated automatically** from the published formula and the values in force (HU-13), with a preview for the Admin before confirming (HU-27). There is no separate approval step.
37. **Formula lock.** An Admin can lock and unlock the publication of a formula, giving a reason; while locked, HU-27 and HU-28 changes are rejected. It is independent from the 14-day season cut-off of HU-28 (HU-27 scenario 11).
38. **Rules version 1 is created by the Admin** when publishing the formula; it is not seeded. This corrects HU-28 and the roadmap.
39. **Decimal arithmetic** for parameter values, limits, the sum rule and rounding (scoring model, rule 8).
40. **Messages and codes of HU-27 and HU-13 are defined during implementation** and added to the specs in the same PR. This is an exception to the Definition of Ready; it needs an amendment of `docs/constitution.md` section 3 (2 approvals).
41. **Version history is outside the MVP.** There is no history of rules versions (HU-27, HU-28) and no history of previous rankings (HU-25). Each rules version is still stored unchanged, and each ranking records the one it used, so HU-13's notice and the Socio views anchored to the latest ranking keep working. The audit keeps who, when and the previous and new values. HU-25, the ranking run itself, stays in the MVP.

## Defaults set by this revision (change them in one place)

Default class B for Partidos not classified in time and 20 default points for institutional events without points when the automatic publication runs; row-error tolerance of 5% for CSV files; code, session and lockout parameters; time zone Buenos Aires; attendance window of previous calendar year plus current year to date; rounding to two decimals; minimum 5 minutes between wave openings; roster staleness limit of 24 hours; 60-minute expiry for paged loads; size limits of decision 27; HU-29 target of under 3 seconds up to 50,000 Socios and under 10 seconds up to 500,000.

## Open items

- **Socio type for HU-30**: the backlog suggests segmenting by "tipo de socio", but the club does not send that field. It needs the club to add it to the roster (HU-43).
- **HU-16, HU-18, HU-29 and HU-30 with other formulas**: they are written for the components of the scoring model v1. When a second formula enters the catalog they must read their components from its descriptor. Not needed in the MVP, which ships one formula.
- **Constitution amendment** for decision 40 (DoR exception): written in `docs/constitution.md` 1.1.0; it still needs the 2 approvals of its PR.

## Interpretations to confirm (not blocking)

- Publishing a different formula or a newer version prefills the values in force for the parameters that exist in both with compatible limits, and the defaults for the rest (HU-27 scenario 8).
- The lock needs a reason both to lock and to unlock, and any Admin of the club can unlock.

- Attendance at elections and assemblies is loaded like any other event attendance (HU-24).
- When nobody defines the points of an institutional event before the automatic publication, a default applies (a system setting, proposed 20).
- The points of an institutional event are limited to a whole number from 1 to 100, matching the maximum of the participation cap.
- The performance targets for 500,000 Socios (HU-25 under 15 minutes, HU-29 under 10 seconds, HU-43 under one hour) are proposals to validate with a load test.

## Backlog changes still required

The backlog already describes the push model for HU-21 and HU-43. Pending:

- Replace "Dirigente" and "Administrador de Sistemas" with the single Admin role (decision 22) in HU-06, HU-07, HU-08, HU-10, HU-28, HU-29 and HU-30. HU-07 no longer chooses a role, and HU-06 has one home screen.
- HU-24 still says "obtener los datos del club": the club sends them (decision 12). Its 5% tolerance applies only to CSV files (decision 23).
- HU-23 still says the Admin requests the update "consultando la información vigente del club": the club sends it and the Admin approves it. Its criterion "respetan las reglas de reprogramación establecidas en HU-23" refers to the story itself; it should say "las reglas siguientes".
- HU-01 says the account is activated when the identifier matches; it is activated after the emailed code (decision 5).
- HU-06: the first criterion says that choosing "Acceso Socio" shows the form (it is the Admin access), and "El socio ingresa el código" should say the Admin.
- HU-21 repeats the audit criterion twice and has no "Criterios de Aceptación" heading.
- The row of HU-26 (Exportación de Listado Priorizado) has "0" instead of its number.
- HU-36 ("Un evento retirado invalida su segmentación") and HU-39 ("Para un evento retirado se informa...") describe effects of HU-23, which is outside the MVP; move those criteria to HU-23 (decision 33).
- HU-38 (outside the MVP) still mentions Socios excluded "con asiento transferido", a feature that no longer exists.

## Residual risks

- Socios are not notified by email when an event changes (HU-19/20 are out): they see the change only when they open the app.
- The wave schedule is informative: with no reservation, ticket-office export or notifications in the MVP, nothing enforces it. State this clearly in the demo.
- Using age as a score component is a policy choice the club should be able to defend before its Socios.
- The freshness of the ranking depends on the club sending its data on time; the 24-hour staleness warning is the safeguard.
- Without HU-23 in the MVP, a published event the club reschedules or cancels keeps its old data until HU-23 is built.

## Review corrections (`CORRECCIONES_SPECS.txt`, applied in v4.1)

| Item of the review | Resolution | Where |
|---|---|---|
| Versioned constitution with numeric thresholds | Written: coverage ≥ 80 % (`app/`) and ≥ 95 % (scoring), DoR/DoD, branches, Conventional Commits, protection of `main`, amendments | `docs/constitution.md` |
| HU-01 sc. 4 / FR-004 "clear error message" | Exact texts and codes for the four cases | HU-01, decision 24 |
| HU-05, HU-08 "partially masked" | `j***@gmail.com` format | cross-cutting §3, decision 25 |
| HU-17 sc. 4 "informative message" | "No hay eventos próximos publicados." | HU-17, decision 24 |
| HU-21 "rejected or reported as non-publishable" | Rejected only (`422 INSUFFICIENT_LEAD`) | HU-21 sc. 7, decision 26 |
| HU-24 "too large", "tens of thousands" | 10 MB / 100,000 rows; 10,000 records per page | HU-24, data contract §3–5, decision 27 |
| HU-24, HU-43 "critically interrupted", "reliable delta" | 60-minute expiry; watermark rule | HU-24, HU-43, data contract §5, decisions 28–29 |
| HU-24 "loads start when the Admin asks" | Already removed in v4: loads start when the club sends them or the Admin uploads a file | HU-24 edge cases |
| Email delivery failure (HU-01, 05, 06, 07) | Error, code discarded, immediate retry (cooldown counts only sent codes); HU-07 undoes the creation, no resend | HU-01, 05, 06, 07, cross-cutting §3, decision 30 |
| Baja of a Socio with account or session | Login and activation refused, sessions revoked | HU-43, HU-01, HU-05, decision 31 |
| HU-17 vs "visible until the end of the day" | The contract no longer has that rule; HU-17 states both types leave at their start | HU-17, decision 32 |
| HU-23 referenced from MVP specs | References removed from HU-17, HU-22, HU-36, HU-37, HU-39 and cross-cutting §4; effects kept in HU-23 | decision 33 |

Where the code does not match the specs yet: [`docs/brechas-codigo.md`](../docs/brechas-codigo.md).

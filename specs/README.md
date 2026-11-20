# MVP Specs Index (v4.9)

30 specs: the 26 stories the backlog marks as MVP, HU-44 (added by the team, MVP, not in the backlog yet), plus HU-42 and HU-23B (outside the MVP, kept as ready specs) and HU-23 (superseded by HU-23B, kept as reference), and 4 shared documents. Titles, estimates, priorities and MVP scope follow the backlog (`Backlog - US.csv`). v4 aligns the specs with the backlog and with the integration prototypes: **the club sends its data to an API the system exposes; the system never calls the club.** v4.1 applies the review in `CORRECCIONES_SPECS.txt` (decisions 24–33 and the table at the end). v4.2 reworks HU-27 and HU-13 around a formula catalog and per-club rules (decisions 34–40). v4.3 reworks HU-29 and HU-30 around four business questions of the Admin: who is rewarded, whom the change harms or favors, which parameter causes the effect and whether the ranking flattens (decisions 44–48). v4.4 brings HU-19 and HU-20 into the MVP: in-app notifications and their email channel, with per-type and general preferences (decisions 50–60). v4.5 makes HU-23 notify its approved changes, withdrawals and restorations through the notifications contract, adding two types to the catalog (decision 61). v4.6 replaces HU-23 with HU-23B: the Admin reprograms the date and time of a published event, merging the waves the new start overlaps, or withdraws it for good with a generic notice to the Socios (decision 62). v4.7 notifies the Socios when the Admin confirms the wave schedule of a Partido, with the start of their own wave (decision 63). v4.8 adds HU-44, the top 10 of each score pillar of the ranking in force for the Admin, and indexes the HU-42 spec (decision 64). v4.9 drops the automatic publication of HU-22: a pending event that nobody publishes by its deadline becomes `expired` and stays that way (decision 65).

## Shared documents

| Document | Purpose |
|---|---|
| [Scoring model v1](_shared/scoring-model.md) | The base formula, parameters with defaults and confirmed limits, calculation rules, worked example |
| [Data contract](_shared/data-contract.md) | Socio, event, attendance and activity data, and the integration API the club calls |
| [Notifications](_shared/notifications.md) | The catalog of notification types, recipients, texts, destinations, generation contract and email delivery rules (HU-19, HU-20) |
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
| HU-15 | [Event History and Rules Applied](hu-15-event-history/spec.md) | 3 | Media | **No** (to be confirmed) |
| HU-16 | [Score Breakdown](hu-16-score-breakdown/spec.md) | 3 | Media | Yes |
| HU-17 | [Upcoming Events](hu-17-upcoming-events/spec.md) | 3 | Alta | Yes |
| HU-18 | [Attendance Score Simulator](hu-18-attendance-score-simulator/spec.md) | 8 | Media | Yes |
| HU-19 | [Configure Email Notifications](hu-19-notification-email-preferences/spec.md) | 3 | Baja | Yes |
| HU-20 | [Notification Inbox](hu-20-notification-inbox/spec.md) | 2 | Baja | Yes |
| HU-21 | [Receive Events Sent by the Club](hu-21-club-event-reception/spec.md) | 5 | Alta | Yes |
| HU-22 | [Define Event Category (Class A/B/C) or Points and Publish](hu-22-event-class-and-publication/spec.md) | 5 | Alta | Yes |
| HU-23 | [Event Reprogramming, Withdrawal and Restoration](hu-23-event-reprogramming/spec.md) — superseded by HU-23B | 5 | Media | **No** |
| HU-23B | [Event Reprogramming and Withdrawal by the Admin](hu-23b-event-reprogramming-and-withdrawal/spec.md) | to be defined | Media | **No** |
| HU-24 | [Load Attendance and Recurring Activities from the Club](hu-24-attendance-load/spec.md) | 5 | Alta | Yes |
| HU-25 | [Ranking Calculation](hu-25-ranking-calculation/spec.md) | 8 | Alta | Yes |
| HU-27 | [Publish the Base Scoring Formula](hu-27-base-formula-publication/spec.md) | 2 | Media | Yes |
| HU-28 | [Adjust Scoring Parameters](hu-28-scoring-weights-adjustment/spec.md) | 5 | Media | Yes |
| HU-29 | [Rules Change Simulation](hu-29-rules-change-impact-simulation/spec.md) | 8 | Media | Yes |
| HU-30 | [Equity Analysis of a Rules Simulation](hu-30-equity-analysis/spec.md) | 5 | Media | Yes |
| HU-36 | [Wave Segmentation](hu-36-wave-segmentation/spec.md) | 8 | Alta | Yes |
| HU-37 | [Wave Schedule](hu-37-wave-schedule-generation/spec.md) | 3 | Alta | Yes |
| HU-39 | [Own Slot](hu-39-own-reservation-slot/spec.md) | 2 | Alta | Yes |
| HU-42 | [Executive Scoring and Equity Report](hu-42-executive-score-report/spec.md) | 3 | Baja | **No** (decision 48) |
| HU-43 | [Receive and Update the Socio Roster Sent by the Club](hu-43-club-roster-reception/spec.md) | 8 | Alta | Yes |
| HU-44 | [Rankings by Score Pillar](hu-44-pillar-rankings/spec.md) | 3 | Media | Yes (not in the backlog yet) |

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
11. **Minimum publication lead: 48 hours** before the event start. The publication deadline is the earlier of 24 hours after the event is received and 48 hours before the start; there is no automatic publication (decision 65).
12. **The club sends, the system receives.** The Socio roster (HU-43), events (HU-21), attendance and recurring activities (HU-24) arrive through an integration API the system exposes, authenticated with a Bearer token per club. The system never calls an API of the club (data contract, section 5).
13. The attendance simulator (HU-18) shows the projected scores exactly (official calculation over the latest ranking, with the Socio's current distance) and, for a Partido, the position as a labeled probabilistic range: each other Socio attends with a smoothed probability from their own history, and the position is 1 plus the sum of the probabilities of ending above. The range is shown by default; if the Admin turns the projection off for the club, the Socio sees only the scores (decision 43). For institutional events it shows the scores and a notice, without a position. The current score and position stay those of the ranking, which used the previous distance if the Socio's home changed.
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
42. **HU-18 position scope**: the estimated position is for Partidos only; institutional events show scores and a notice (decision 13). It uses what the ranking snapshot already stores and does not change HU-25.
43. **HU-18 position projection on by default, set by the Admin.** `position_projection_enabled` starts on for every club, without a prior validation, because the simulation never changes the real ranking or any stored data and every estimated position carries the estimate label. The Admin reads and changes the four simulator settings of their own club, with validation and audit (HU-18 scenario 14, FR-013). The offline validation of HU-18 (coverage and error against the frozen-others version) stays as a recommended check to tune `k` and the range level or to turn the projection off.
44. **HU-29 baseline and validation.** The baseline is the latest completed ranking, as stored, and the form is pre-filled with its rules version; when the rules in force differ, the Admin is told and can load them into the form to anticipate the next calculation. A simulation uses the limits, sum rule, codes and texts of HU-27 and is **not** blocked by the formula lock or the season cut-off of HU-28, which govern saving official rules, not previewing them. Each result uses one ranking and shows its date and rules version.
45. **HU-29 results.** For the ranking and the simulation side by side: histogram (20 bins of 5 points), mean, median, standard deviation and 10th and 90th percentiles; Socios up, down and unchanged, mean absolute change of position and relevant movements (a relevant movement is `m = max(1, ceil(N/100))` positions, 1 % of the ranking); Socios at the cap of 100, Socios needing a cap adjustment, tied Socios and the largest tie, with saturation and flatness alerts; and the mean change per score component, whose changes add up to the change of the mean total.
46. **HU-29 effect by parameter.** The changed parameters are grouped in factors: pillar weights (always together, because each alone breaks the sum rule), `αA`, `dsat` and other parameters. When two or more factors changed, each changed factor among pillar weights, `αA` and `dsat` is simulated on its own (at most three extra simulations) and ordered by mean absolute change of position; the rest, with the other parameters and the interactions, is shown as a remainder because the effects are not additive. The breakdown is shown after the main result and never blocks it. Targets 9 s (up to 50,000 Socios) and 30 s (up to 500,000) are proposals to validate with a load test.
47. **HU-30 profile and equity.** Next to the simulation: the profile of the Socios who move up and down, against all Socios (distance, seniority, age, attendance at Clase C matches, institutional participation; medians; no group under 10 Socios shown), and the equity by seniority, distance and age in fixed bands with a deterministic merge rule for segments under 10 Socios. A segment is marked when its mean change of position is 2 % of the ranking or more, and strong at 5 %; there is a verdict per attribute and an overall one (`EQUITY_OK`, `EQUITY_ATTENTION`, `EQUITY_BIAS`). The thresholds (1 %, 80 %, 10 Socios, 2 %, 5 %) are fixed in the product, not settings; changing them is an amendment of the spec. Segmenting by "tipo de socio" stays out until the club sends that field.
48. **The simulator never applies values.** HU-28 remains the only way to change the rules, with its cut-off, lock and confirmation. The result lists the changed parameters with their previous and hypothetical values, and can be downloaded as a CSV generated at that moment and never stored. Simulations change nothing and are not audited. A stored or executive report is HU-42, outside the MVP.
49. **The tiebreak lives in the snapshot.** Each ranking entry stores, besides the dates of rule 5, the Socio's document number (scoring model, rule 4), so HU-18, HU-29 and HU-30 rebuild the exact order from the snapshot without re-reading the roster. Entries calculated before this decision are completed once from the roster by a data migration.

61. **HU-23 notifies through the notifications contract.** Approving a change generates `event_rescheduled` (now active); withdrawing a published event generates `event_withdrawn` and restoring it generates `event_restored`, two types the team added to the catalog, which goes from four to six types. Each is generated after the action commits, for every Socio of the club with an `activated` account, and never undoes the action. The withdrawal text includes the Admin's reason as written. The separate queue of the first HU-23 implementation (`notificaciones_eventos`) is removed. This replaces the earlier rule that a withdrawal does not notify (notifications sections 2 to 4, HU-23 edge cases).
62. **HU-23B replaces HU-23.** The Admin works from the list of published events that have not started. **Reprogramming** changes only the date and time: the type, the class or points (HU-22 scenario 9, FR-008) and the club fields never change, and there is no club change review, no 24-hour window and no `pending review` state; changes the club sends for a published event stay omitted. When the new start overlaps a confirmed schedule, the waves that have not opened and would open after the new start, or less than the minimum step before it, join the last unaffected wave; the general closing becomes the new start and the other waves keep their starts; if every wave is affected the schedule is invalidated. **Withdrawal** asks only for a confirmation, is final (no restoration, the event disappears for Socios and Admins), deletes the segmentation and the schedule and notifies every Socio with a generic text. Notifications: `event_rescheduled` on every reprogramming, the new type `wave_rescheduled` (or `wave_opened` right away when the target wave already opened) for the moved Socios, `event_withdrawn` renamed "Evento suspendido" without the reason, and `event_restored` inactive. This replaces decisions 20 and 33 where they name HU-23, and the withdrawal and restoration parts of decision 61 (HU-23B, notifications sections 2 to 4).
63. **Confirming a schedule notifies its Socios.** When the Admin confirms the wave schedule of a Partido (HU-37), every Socio of every wave with an `activated` account gets the new type `wave_schedule_confirmed` ("Ya tenés tu turno de reserva") with the start of their own wave, after the confirmation commits. A new confirmation after a regeneration notifies again with the new times. It opens the Socio's slot (HU-39), like `wave_opened`, which still notifies the opening of each wave. The catalog grows to seven active types (notifications sections 2 to 4, HU-19 scenarios 10 and 11).
64. **Rankings by score pillar (HU-44).** Besides the general ranking, the Admin sees the top 10 of each pillar of the ranking in force: Asistencia (frequency plus distance), Participación institucional and Antigüedad y edad, with the points of the HU-16 breakdown and without the new-member bonus or the cap adjustment. They are derived from the stored entries of that run when read, so nothing is copied per Socio, the HU-25 run is unchanged and the four rankings always come from the same run. Only Socios with points in the pillar are listed. Ties, including many Socios at the bound of a saturated pillar, follow the general ranking tiebreak (seniority, age, lower document number), with no count of tied Socios. A pillar without points shows "Ningún socio sumó puntos en este pilar en el último cálculo."; a formula that does not declare its pillars shows "La fórmula de este ranking no define rankings por pilar.". Read-only, Admin only, not audited, and with no response-time target. The HU-42 spec is indexed as written; it stays outside the MVP (decision 48, backlog).
65. **No automatic publication; missed deadlines expire.** Only an Admin publishes an event (HU-22), and only before its publication deadline (decision 11). A pending event that nobody published by then becomes `expired`: it is never published, gets no class or points, is never visible to Socios, accepts no attendance, generates no notification and cannot be published, discarded or reopened afterwards; the club's resends and updates of it are omitted (HU-21). Expiry is derived from the deadline, so HU-22 needs no scheduled job, and the default class (Clase B) and points (20) at the deadline disappear; those values remain only as the prefill when the Admin confirms a historical event (HU-21 scenario 11). A cancellation from the club no longer withholds anything. This replaces the automatic publication of decision 11 and of HU-22 scenarios 6 to 8, FR-005, SC-001 and SC-002 (HU-22 v5, HU-21, HU-19, notifications sections 2 and 4, cross-cutting sections 4, 7 and 8).

## Defaults set by this revision (change them in one place)

Clase B and 20 points proposed when the Admin confirms a historical Partido or institutional event (HU-21); row-error tolerance of 5% for CSV files; code, session and lockout parameters; time zone Buenos Aires; attendance window of previous calendar year plus current year to date; rounding to two decimals; minimum 5 minutes between wave openings; roster staleness limit of 24 hours; 60-minute expiry for paged loads; size limits of decision 27; HU-29 target of under 3 seconds up to 50,000 Socios and under 10 seconds up to 500,000 (9 and 30 seconds for its effect by parameter); fixed thresholds of HU-29 and HU-30 (decisions 45 and 47); 20 notifications per page, email batches of 500, a 60-minute catch-up window for wave openings and no expiry of notifications (notifications section 7).

## Open items

- **Socio type for HU-30**: the backlog suggests segmenting by "tipo de socio", but the club does not send that field. It needs the club to add it to the roster (HU-43).
- **HU-16, HU-18, HU-29 and HU-30 with other formulas**: they are written for the components of the scoring model v1. When a second formula enters the catalog they must read their components from its descriptor. Not needed in the MVP, which ships one formula.
- **Position of institutional events in HU-18**: not estimated in this version because the inputs snapshot (HU-25, scoring model rule 4) does not hold the number of institutional events each Socio could attend in the window. Adding it needs that data in the snapshot and a revision of HU-18. Until then HU-18 shows scores and a notice for those events.
- **Thresholds of HU-29 and HU-30**: the relevant movement (1 %), the flatness alert (80 %), the marks of the equity analysis (2 % and 5 % of the ranking) and the minimum group (10 Socios) are proposals to review with the club on real simulations (decisions 45 and 47).
- **Constitution amendment** for decision 40 (DoR exception): written in `docs/constitution.md` 1.1.0; it still needs the 2 approvals of its PR.

- **Estimate of HU-19**: the backlog says 3, but it now covers preferences, generation of six active types (decisions 61 and 62), a dispatch queue and a periodic job. It is a candidate for re-estimation.
- **`FRONTEND_BASE_URL`** must be configured per environment for the email buttons.
- **Retention** of notifications is open: they are kept without expiry in the MVP.

## Interpretations to confirm (not blocking)

- Publishing a different formula or a newer version prefills the values in force for the parameters that exist in both with compatible limits, and the defaults for the rest (HU-27 scenario 8).
- The lock needs a reason both to lock and to unlock, and any Admin of the club can unlock.

- Attendance at elections and assemblies is loaded like any other event attendance (HU-24).
- The points of an institutional event are limited to a whole number from 1 to 100, matching the maximum of the participation cap.
- The performance targets for 500,000 Socios (HU-25 under 15 minutes, HU-29 under 10 seconds and its effect by parameter under 30 seconds, HU-43 under one hour) are proposals to validate with a load test.

## Backlog changes still required

The backlog already describes the push model for HU-21 and HU-43. Pending:

- Replace "Dirigente" and "Administrador de Sistemas" with the single Admin role (decision 22) in HU-06, HU-07, HU-08, HU-10, HU-28, HU-29 and HU-30. HU-07 no longer chooses a role, and HU-06 has one home screen.
- HU-24 still says "obtener los datos del club": the club sends them (decision 12). Its 5% tolerance applies only to CSV files (decision 23).
- Replace HU-23 with HU-23B (decision 62): the Admin reprograms the date and time of a published event or withdraws it for good, with the wave merge and the suspension notice; no club change review, no restoration, no class or points change.
- HU-01 says the account is activated when the identifier matches; it is activated after the emailed code (decision 5).
- HU-06: the first criterion says that choosing "Acceso Socio" shows the form (it is the Admin access), and "El socio ingresa el código" should say the Admin.
- HU-21 repeats the audit criterion twice and has no "Criterios de Aceptación" heading.
- The row of HU-26 (Exportación de Listado Priorizado) has "0" instead of its number.
- HU-36 ("Un evento retirado invalida su segmentación") and HU-39 ("Para un evento retirado se informa...") describe effects of a withdrawal, which is outside the MVP; move those criteria to HU-23B (decisions 33 and 62).
- HU-44 (Rankings by Score Pillar, 3 points, Media, MVP) is not in the backlog: add it (decision 64).
- HU-22 still describes the automatic publication with Clase B or 20 points by default, and HU-21 says a cancellation "evita su publicación automática": a pending event not published by its deadline becomes `expired` instead (decision 65).
- HU-42: its spec says MVP, the backlog and decision 48 say it is outside the MVP; align the spec header.
- HU-38 (outside the MVP) still mentions Socios excluded "con asiento transferido", a feature that no longer exists.
- HU-19 and HU-20 enter the MVP and need their criteria completed in the backlog: a general email switch besides the per-type ones, the types of the catalog and where each opens, the exact texts, that preferences never affect the inbox, that failures never block the triggering process, "mark as read" (one and all) and the counter in the menu.
- HU-29 and HU-30 in the backlog still describe the original scope. Align their criteria with the specs (business questions, baseline and pre-fill, saturation and ties, change per component, effect by parameter, profile of the movers, equity with verdict, CSV) and re-estimate them (decisions 44–48).

## Residual risks

- Socios are notified when an event is published, a wave opens or a ranking completes, but a reprogramming or withdrawal of a published event is notified only where HU-23B (outside the MVP) is deployed; without it they see nothing until they open the app (decision 62).
- With HU-23B the Admin types the new date and time of an event that the club informs by another channel; a typing error reaches every Socio as a notification. The preview before confirming is the safeguard.
- Notifications are best effort with no retries: a failed email or a crash between a change and its notification is not recovered. The inbox and the app screens remain the reliable source.
- The wave schedule is informative: with no reservation or ticket-office export in the MVP, nothing enforces it, even though Socios are now notified when their wave opens. State this clearly in the demo.
- Using age as a score component is a policy choice the club should be able to defend before its Socios.
- The verdict of HU-30 is descriptive: it applies fixed thresholds to three attributes (seniority, distance, age); it is not a statistical test and does not certify the absence of bias in other attributes.
- HU-29 and HU-30 work on the snapshot of the latest ranking: they do not age the Socios, shift the attendance window or reflect later loads. To see the current situation the Admin runs HU-25 first.
- The freshness of the ranking depends on the club sending its data on time; the 24-hour staleness warning is the safeguard.
- Without HU-23B in the MVP, a published event the club reschedules or cancels keeps its old data until HU-23B is built.

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

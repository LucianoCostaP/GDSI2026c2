# Scoring Model v1 (Base Formula)

**Status**: Adopted. This is the **first entry of the formula catalog** (id `scoring-model`, version 1) and the base formula referenced by HU-13, HU-14, HU-16, HU-18, HU-25, HU-27, HU-28, HU-29 and HU-30. Its structure is fixed in the product; the Admin of each club publishes a formula of the catalog (HU-27); after that only its parameters (section 4 for this formula) are editable (HU-28). Section 7 explains how the catalog grows.

## 1. Global score

```
S = min(100, wA·P_asistencia + wP·P_inst + wT·P_antigüedad + B_nuevo)
```

- The result is bounded to [0, 100]. The cap is applied to the **total**, after adding the new-member bonus.
- Constraint: `wA + wP + wT = 1.00` (two decimals). Defaults: 0.60 / 0.20 / 0.20.

## 2. Pillars

### 2.1 Attendance (P_asistencia)

```
P_asistencia = (1 − αA)·P_frecuencia + αA·P_distancia
```

**Frequency by event class**

```
P_frecuencia = 100 · Σ_attended C(Ii) / Σ_total C(Ij)
```

| Event class | Meaning | Factor C(I) |
|---|---|---|
| Clase A | Superclásicos / high-demand definitions | 1.0 |
| Clase B | Regular league matches | 1.3 |
| Clase C | Low-demand / adverse-condition matches | 1.8 |

The factors are constants of the formula (not editable). A higher factor means **lower** demand: the club rewards attending the matches that are harder to fill.

- Only events of type "Partido" inside the attendance window count. Events of type "Evento institucional/amateur" score in the institutional pillar (section 2.2).
- Only events that already took place **and** have an attendance load (HU-24) count in the denominator. A match whose attendance has not been loaded is ignored, not counted as an absence.
- For a Socio, the denominator counts only events on or after `max(alta date, window start)`.
- Denominator = 0 → `P_frecuencia = 0`.

**Distance effort (Gompertz)**

```
P_distancia = (1 / N_asistidos) · Σ_attended 100 · exp( −exp( −b·(di − dsat) ) ),   b = 4.356 / dsat
```

- `dsat` is the **inflection point** of the curve: at `di = dsat` the value is 36.8 %. The curve reaches about 95 % at 1.68·dsat and about 98.7 % at 2·dsat. A Socio living far below `dsat` gets almost no distance credit.
- `b` is derived from `dsat`, never edited directly. Reference profiles: Local `dsat = 150 km (b = 0.0290)`, Regional `400 km (b = 0.0109)`, Nacional `1200 km (b = 0.0036)`.
- `di` is the Socio's distance in km to the stadium (see `data-contract.md`).
- `N_asistidos = 0` → `P_distancia = 0`.

**Attendance window**: previous calendar year plus current year to date, up to the calculation date. Every event in the window has the same weight (only its class factor differs).

### 2.2 Institutional participation (P_inst)

```
P_inst = min(Pinst_max, Σ_k (Vk·Ak) + Σ_m (Dm·tm))
```

| Item | Points |
|---|---|
| Institutional event (Vk): elections, assemblies and any other Evento institucional/amateur | points defined by whoever publishes the event, a whole number from 1 to 100 (reference values of the original formula: election 50, assembly 40) |
| Deporte Federado (Dm) | 10 per month |
| Subcomisiones (Dm) | 15 per month |

- Elections, assemblies and every other "Evento institucional/amateur" are events: loaded with HU-21, published with their points (HU-22) and attendance loaded with HU-24. This includes events held at venues other than the club stadium. Only recurring activities are loaded as records, through HU-24.
- `Ak = 1` when a participation record exists for the Socio and the event, otherwise 0. `tm` = number of months of activity.
- Moving expiration of 365 days: only records whose date (or, for activities, the months) fall inside the last 365 days before the calculation date count. `tm` is capped at 12 per activity.
- The points of recurring activities are constants of the formula (federated sport 10 per month, subcommission 15 per month). The points of each institutional event are set at its publication and cannot change afterwards in the MVP. `Pinst_max` (default 100) is editable.
- Recurring activities enter through HU-24; institutional events (elections and assemblies included) enter through HU-21, HU-22 and the attendance load of HU-24.

### 2.3 Seniority and age (P_antigüedad)

```
P_antigüedad = 100 · min(1, [ (αT·T + (1 − αT)·E) / (αT·Tref + (1 − αT)·Eref) ]^γ )
```

- `T` = years of uninterrupted membership, `E` = age in years, both at the calculation date.
- Age is a **component of the score**, not only a tiebreak. It is a policy decision that the club must be able to defend to its Socios.

## 3. New-member bonus (B_nuevo)

Version 1 uses the **linear** option only (the exponential option needs a λ that is not in the parameter matrix):

```
B_nuevo = Bmax · max(0, 1 − t / Tmax)      t = days since alta
B_nuevo = 0  if the Socio had a previous baja less than tcarencia days before the new alta
```

A Socio with no previous baja gets the bonus. `t ≥ Tmax` → 0.

## 4. Configurable parameters

All parameters in this table are editable by an Admin (HU-28), subject to the limits shown. The limits are **confirmed by the club** (the column header "Proposed" is kept only for history). The initial values are chosen at publication (HU-27) within the same limits.

| Parameter | Symbol | Default | Limits (confirmed) |
|---|---|---|---|
| Pillar weights | wA / wP / wT | 0.60 / 0.20 / 0.20 | each 0.00–1.00, sum = 1.00 |
| Distance weight inside attendance | αA | 0.20 | 0.00–1.00 |
| Distance saturation (inflection) | dsat | 1200 km | 50–3000 km |
| Institutional participation cap | Pinst_max | 100 pts | 1–100 pts |
| Seniority weight vs. age | αT | 0.70 | 0.00–1.00 |
| Seniority reference | Tref | 50 years | 10–100 |
| Age reference | Eref | 80 years | 40–120 |
| Curvature | γ | 1.0 | 0.5–1.0 |
| Welcome bonus | Bmax | 15.0 pts | 5.0–25.0 |
| Bonus extinction window | Tmax | 180 days | 30–365 |
| Re-entry grace period | tcarencia | 365 days | 0–1095 |

## 5. Calculation rules

1. **Rounding**: each component is rounded to 2 decimals (half up). The total is the sum of the rounded components. Ranking order uses this 2-decimal total.
2. **Cap**: if the sum of components exceeds 100, a component "Ajuste por tope" with the negative difference is added so the total equals 100. This keeps the breakdown (HU-16) equal to the total (HU-14).
3. **Score components stored per Socio** (see HU-16): `attendance_frequency`, `attendance_distance`, `institutional`, `seniority_age`, `new_member_bonus`, `cap_adjustment`. Components are the weighted contributions (for example `wA·(1−αA)·P_frecuencia`).
4. **Inputs snapshot**: each ranking stores, per Socio, the raw inputs (class-weighted sums, distance terms, distance `di`, participation points, T, E, t) so that HU-18, HU-29 and HU-30 can recompute or segment under other parameters without re-reading source data.
5. **Tiebreak**: equal totals are ordered by greater seniority, then greater age, then lower document number (HU-25).
6. **Versioning**: every change of parameters creates a new rules version (HU-28). Every ranking records the rules version it used.
7. **Eligibility**: only Socios with fees up to date at the calculation time appear in the ranking. Attendance and participation history is kept for every Socio whatever their fee status, so a Socio who pays up returns to the ranking with their accumulated record (inside the windows). Nothing is deleted when fees lapse.
8. **Decimal arithmetic**: parameter values, limits, the sum rule and the rounding of components use decimals (`Decimal`), never binary floating point. Only the curve functions (`exp`) may use floating point, and their result is rounded as in rule 1.
9. **Scope of the rules**: rules 1, 5, 6, 7 and 8 are common to every formula of the catalog. Rules 2, 3 and 4 (cap adjustment and the named components) describe this formula; another formula defines its own components in its descriptor, keeps the total inside [0, 100], rounds to two decimals and stores its components and its inputs snapshot.

## 6. Worked example (defaults)

Socio at 1200 km. Window: 20 official matches (4 Clase A, 10 B, 6 C); attended 3 A, 6 B, 5 C. One Asamblea (40) and 3 months of Deporte Federado (30). T = 10 years, E = 45 years. Not a new member.

| Step | Value |
|---|---|
| P_frecuencia = 100 · 19.8 / 27.8 | 71.22 |
| P_distancia (di = dsat) | 36.79 |
| P_asistencia = 0.8·71.22 + 0.2·36.79 | 64.34 |
| P_inst = min(100, 40 + 30) | 70.00 |
| P_antigüedad = 100 · 20.5 / 59 | 34.75 |

| Component | Points |
|---|---|
| Asistencia – frecuencia (0.6·0.8·P_frecuencia) | 34.19 |
| Asistencia – distancia (0.6·0.2·P_distancia) | 4.41 |
| Participación institucional (0.2·70) | 14.00 |
| Antigüedad y edad (0.2·34.75) | 6.95 |
| Bonus nuevo socio | 0.00 |
| Ajuste por tope | 0.00 |
| **Total** | **59.55** |

## 7. Formula catalog

The product ships a **catalog** of formulas. Each entry is a *descriptor* plus its calculation:

- **Descriptor**: id, name, version, description, variables, parameters (key, symbol, name, unit, default, limits), constants, derived values (for example `b`), constraints (for example `wA + wP + wT = 1.00`) and the **explanation template** in Spanish with placeholders for the parameters (HU-13).
- **Calculation**: one pure, deterministic implementation per formula, used by HU-25, HU-18, HU-29 and HU-30 (constitution, principle 1), with unit tests against a reference dataset.
- **Adding a formula** is a product release: new descriptor, its calculation if its structure is new, its tests and its explanation template reviewed by the club. The Admin cannot create or edit formulas from the screen.
- **Validation in tests**: every default lies within its limits, every range is valid and every template placeholder is a parameter of the formula.
- **Publication** (HU-27): the Admin of a club chooses an entry of the catalog and publishes it with initial values; that creates a rules version of the club. The rules of each club are independent.
- **This file** describes the entry `scoring-model` version 1, the only one in the MVP.

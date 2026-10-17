# Feature Specification: Analyze Equity in a Rules Simulation

**Feature Branch**: `hu-30-rules-equity-analysis`  
**Created**: 2026-10-17  
**Status**: Draft  
**Backlog Reference**: HU-30 (Estimate: 5, Priority: Media, MVP: Yes)  
**Shared rules**: [scoring model](../_shared/scoring-model.md), [cross-cutting](../_shared/cross-cutting.md)  
**Related spec**: [HU-29 Rules Change Simulation](../hu-29-rules-change-impact-simulation/spec.md)  
**Input**: "As a Dirigente or Administrador, I want to see how hypothetical scoring changes affect different Socio profiles, so that I can spot disproportionate effects before applying a change."

## User Scenarios & Testing

### User Story 1 - Compare Segment Effects (Priority: P2)

As a Dirigente or Administrador, I want aggregate comparisons for Socio segments in the current HU-29 simulation so I can inspect whether the hypothetical rules shift outcomes unevenly.

**Why this priority**: Makes the overall simulation more interpretable by showing how aggregate outcomes differ across available member profiles.

**Independent Test**: Run HU-29 with valid hypothetical parameters and verify aggregate before/after score and position summaries by supported segments appear with the general simulation; verify the real ranking and member records are unchanged.

**Acceptance Scenarios**:

1. **Given** a completed HU-29 simulation, **When** the user opens the equity analysis, **Then** the analysis uses that same simulation and baseline without running a second or different simulation.
2. **Given** simulation results, **When** the user views the analysis, **Then** they can compare average score and average position before and after by supported Socio segments.
3. **Given** several segments, **When** the comparison is displayed, **Then** segments with the largest positive and negative average changes are identified relative to the overall change.
4. **Given** an attribute is not present or not reliable in the ranking snapshot, **When** the user selects segmentation, **Then** it is unavailable and no value is inferred.
5. **Given** a segment has too few members to report safely, **When** results are displayed, **Then** that segment is grouped as “Otros” or suppressed according to the minimum group-size setting; individual Socio results are never exposed.
6. **Given** the user changes HU-29 hypothetical values and reruns the simulation, **When** results are refreshed, **Then** the equity comparisons update from the new simulation.
7. **Given** there is no completed baseline ranking, **When** the user opens the analysis, **Then** the HU-29 no-baseline message is shown.

### Edge Cases

- Supported segments are limited to attributes available in the ranking snapshot and approved for aggregate analysis, initially: tenure bands derived from membership start date and distance bands derived from `distancia_km`.
- “Tipo de socio” is not defined in the shared data contract. Do not offer this segment until the club defines the field and meaning.
- Position movement is interpreted against each Socio's position in the baseline ranking; average position is descriptive and does not imply a new official ranking.
- Segment totals may differ if data is missing; display the included-member count for each segment.

## Requirements

### Functional Requirements

- **FR-001**: System MUST extend the same HU-29 simulation with aggregate segment analysis; it MUST NOT run a separate simulation.
- **FR-002**: System MUST compare average score and average position before and after for supported segments.
- **FR-003**: System MUST identify the segments with the largest positive and negative average score changes relative to the overall change.
- **FR-004**: System MUST show the number of Socios included in each reported segment.
- **FR-005**: System MUST use only attributes available in the stored ranking snapshot and MUST NOT infer missing attributes.
- **FR-006**: System MUST not reveal individual Socio outcomes through this analysis; small segments are suppressed or grouped using a configurable minimum group size.
- **FR-007**: System MUST display these comparisons alongside HU-29's general before/after results.
- **FR-008**: System MUST leave official scores, positions, rules, and member records unchanged.

### Key Entities

- **SegmentImpactSummary**: segment attribute and band, included count, average score and position before/after, score delta, and relation to overall change. Derived and transient.

## Success Criteria

- **SC-001**: Every equity summary is derived from the same simulation and ranking snapshot as HU-29.
- **SC-002**: No individual Socio result is exposed by the analysis.
- **SC-003**: Real ranking data and active scoring rules remain unchanged after any analysis.
- **SC-004**: The segment summaries appear alongside HU-29's general charts and comparison.

## Assumptions and Decisions to Reconcile

- The backlog carries an unresolved note that the scope changed to “solo gráficos” and asks how to update its acceptance criteria. This spec interprets HU-30 as aggregate charts/summaries integrated into HU-29, with no separate simulation flow.
- The backlog's examples include “tipo de socio”, but that field is absent from the shared data contract. This spec initially supports tenure and distance bands only; confirm which profile attributes the club approves and define the minimum group size before implementation.
- Estimate 5 is retained from the current backlog value; re-estimate if the approved segment set or privacy rules materially expand the scope.

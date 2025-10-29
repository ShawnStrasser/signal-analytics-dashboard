# Changepoints Feature Plan

## Status
- Current focus: **Testing and polish** (Step 10)
- Next up: **Verification & handoff**
- Recently completed: Steps 6-9 (map/table/chart integration)
- Open questions: None at this time

## Task Breakdown
1. [x] Review existing architecture and patterns  
   Notes: Confirmed navigation wiring, shared filter mechanisms, map rendering paths, existing API blueprint patterns.
2. [x] Documentation updates  
   Notes: README now references the CHANGEPOINTS schema and the new page; CLAUDE.md calls out styling consistency expectations.
3. [x] Page scaffold  
   Notes: Added route and navigation entry; created `frontend/src/views/Changepoints.vue` with initial layout, legend, map/table/chart placeholders.
4. [x] Filter pane implementation  
   - Extend `FilterPanel.vue` with percent-change controls and hide day/time filters on the changepoints route.
   - Default percent-change filter to less than -1% or greater than +1%; make adjustable.
   - Ensure summary text captures percent-change constraints alongside existing filters.
5. [x] Data querying + store wiring  
   - Added Pinia helpers (`changepointFilterParams`) and persisted percent-change thresholds.
   - Implemented `routes/api_changepoints.py` (map, segment, table, detail endpoints) and wired corresponding ApiService calls.
   - `Changepoints.vue` now loads map/table data reactively (filters + selections), updating selection mappings and keeping state in sync.
6. [x] Map visualization updates  
   Notes: `SharedMap.vue` now handles `data-type="changepoints"` with circle sizing from ABS_PCT_SUM, diverging color scale via `changepointColorScale`, theme-aware legend, and enriched tooltips covering top changepoint metadata for signals and XD segments.
7. [x] Interactive table  
   Notes: Server-side sorting wired to filters/selections (limit 100), row highlight + toggle selection, and summary chips persisted; selection feeds detail view state.
8. [x] Detail chart  
   Notes: Added `ChangepointDetailChart.vue` for before/after travel time series with date/time and time-of-day modes, consistent styling with existing analytic pages.
9. [x] Cross-component interactions  
   Notes: Filters/map selections reset downstream state; watchers coordinate map/table/chart refresh; single-row pipeline drives detail fetch and chart rendering.
10. [ ] Testing and polish  
    - Manual walkthrough across themes, verifying filters, sorting, selections, and tooltips.
    - Double-check documentation references and note any follow-up tasks.

## Notes / Findings
- Navigation entries live in `frontend/src/App.vue` with routes defined in `frontend/src/router.js`.
- Shared filters use `useFiltersStore`; changepoint-specific controls require store updates and route-aware UI logic.
- Map behavior is centralized in `components/SharedMap.vue`; new changepoint logic can hook into existing data-type handling.
- Backend blueprints follow a consistent pattern (`routes/api_*.py`) returning Arrow data; `api_changepoints.py` mirrors this structure.
- Added store state + UI for percent-change thresholds, route-specific filter visibility toggles, and reactive changepoint data loading in the new view.

## Risks / Follow-ups
- Need confirmation that changepoint aggregation data exists or must be computed on the fly; may impact query performance.
- Travel time detail queries must be efficient for per-changepoint before/after windows.

## Handoff Guide
- Latest completed step: Tasks 6-9 (map visuals, table interactions, detail chart, sync wiring).
- To resume: Step 10 verification—run targeted regression (light/dark themes, colorblind toggle, selection resets) and capture QA notes; confirm documentation references remain accurate.

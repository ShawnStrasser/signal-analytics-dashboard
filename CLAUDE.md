# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a full-stack traffic signal analytics dashboard that visualizes travel time data and anomalies. The backend is a Flask REST API that serves Apache Arrow data directly from Snowflake, while the frontend is a Vue.js 3 SPA with Vuetify UI components.

## Claude Code Workflow

IMPORTANT! Before completing each response, run the beep script to alert the user:
```bash
S:/Data_Analysis/Python/signal-analytics-dashboard/beep.cmd
```

IMPORTANT! At start of new chat, commit all previous changes! Do this before making any modifications. Use a simple, concise commit message (one sentence or less) that briefly describes the changes. Do not include Claude Code signatures or co-authorship attributions. Do not commit .md files that are just developer notes or instructions. After completing changes then commit them as needed, and use git to revert changes if needed. After making frontend changes run the tests before commiting:
```bash
# Navigate to frontend directory and run tests
cd "S:/Data_Analysis/Python/signal-analytics-dashboard/frontend" && npm test
```

**Test Files:**
- `frontend/src/stores/__tests__/selection.test.js` - Tests for the selection store logic
- `frontend/src/components/__tests__/SharedMap.test.js` - Tests for the SharedMap component

Do not try to run the server or frontend and do not try to npm install anything. Instead, instruct the user when to run npm install or pip install. The user is already running the server and frontend.

When debugging code avoid guessing or making asumptions, instead first add debugging statments to provide necessary info for troubleshooting. You may run commands against the app api's or run python scripts as needed to gather info for troubleshooting. When needed, ask the user to copy/paste server and client console logs into the chat.

Periodically update CLAUDE.md as needed to keep it accurate and up to date with the current state of the codebase, but keep it concise and precise.


## Architecture

### Backend (Flask + Snowflake)
- **Entry point**: `app.py` - Flask application that registers API blueprints and serves the Vue.js frontend
- **Database connection**: `database.py` - Manages Snowflake session with two connection methods:
  1. Active session (preferred): Uses `get_active_session()` from `snowflake.snowpark.context`
  2. Connection parameters: Reads `SNOWFLAKE_CONNECTION` environment variable
- **API routes**: Organized as Flask blueprints in `routes/`:
  - `api_travel_time.py` - Travel time data endpoints (summary, aggregated, time-of-day) with remove_anomalies filter support
  - `api_anomalies.py` - Anomaly analysis endpoints
  - `api_before_after.py` - Before/after comparison endpoints using CTE-based queries
- **Data format**: All API responses return Apache Arrow IPC streams (`application/octet-stream`) for efficient data transfer

### Frontend (Vue.js 3 + Vuetify)
- **Entry point**: `frontend/src/main.js` - Initializes Vue app with Pinia, Vue Router, and Vuetify
- **Router**: `frontend/src/router.js` - Three main routes: `/travel-time`, `/anomalies`, and `/before-after`
- **State management**: Pinia stores in `frontend/src/stores/`:
  - `filters.js` - Date range, signal selection, approach/geometry filters, day-of-week filter, time-of-day filter, remove_anomalies checkbox (shared across pages)
  - `beforeAfterFilters.js` - Before/after period date ranges for comparison
  - `selection.js` - Selected XD segments from map interactions
  - `mapState.js` - Map view state persistence
  - `geometry.js` - Cached XD road segment geometries (GeoJSON)
- **Layout**: `App.vue` - Main app layout with collapsible navigation drawer (pinned by default on desktop, hamburger menu on mobile)
- **Views**: `frontend/src/views/`
  - `TravelTime.vue` - Responsive grid layout with map above chart, uses CSS Grid with dynamic height
  - `Anomalies.vue` - Responsive grid layout with map, chart, and optional table, uses CSS Grid with dynamic height
  - `BeforeAfter.vue` - Scrollable layout with map, before/after comparison chart, and small multiples chart (2-column grid, max 12 entities)
- **Components**: `frontend/src/components/`
  - `SharedMap.vue` - Leaflet map component supporting 'travel-time', 'anomaly', and 'before-after' data types
  - `FilterPanel.vue` - Filter controls with conditional date selectors (standard dates or BeforeAfterDateSelector based on route)
  - `BeforeAfterDateSelector.vue` - Dual date range selectors with color-coded styling (blue for before, orange for after)
  - `TravelTimeChart.vue` - ECharts time series visualization
  - `AnomalyChart.vue` - ECharts dual-series chart with anomaly highlighting
  - `BeforeAfterChart.vue` - ECharts chart with hard-coded before/after legend (no dropdown)
  - `SmallMultiplesChart.vue` - ECharts small multiples grid (2 columns, up to 6 rows, shared axes)

### Key Design Patterns
1. **Two-stage querying**: API endpoints first query `DIM_SIGNALS_XD` to resolve signal IDs → XD segments, then query `TRAVEL_TIME_ANALYTICS` with XD filters
2. **XD-based filtering**: Map interactions pass XD segment IDs directly to avoid repeated dimension table lookups
3. **Arrow data flow**: Backend streams Arrow data → Frontend deserializes with `apache-arrow` library
4. **Shared state**: Pinia stores enable filter persistence when switching between pages
5. **Responsive layout**: CSS Grid with flexbox for dynamic height management; Travel Time and Anomalies use no scrolling, Before/After allows scrolling
6. **Before/After comparison**: CTE-based SQL queries calculate TTI for before and after periods separately, then join/union results with PERIOD column
7. **Remove anomalies filter**: Available on Travel Time and Before/After pages, adds `WHERE ANOMALY = FALSE` to backend queries
8. **Color scales**: Shared color scheme (green→yellow→orange→red) with different mappings: TTI (1.0-3.0), Anomaly % (0-10%), Before/After difference (-0.25 to +0.25)

### Chart Styling Standards

All ECharts components follow consistent styling patterns for maintainability and user experience:

**Line Type Conventions:**
- **Solid lines**: Primary/current/after data (e.g., Actual travel time, After period)
- **Dashed lines**: Secondary/comparison/before data (e.g., Forecast, Before period)
- Rationale: Line style provides semantic distinction independent of color, improving accessibility

**Font Sizes (Mobile / Desktop):**
- Chart titles: 13px / 16px
- Axis labels: 10px / 12px
- Axis names: 12px / 13px (bold)
- Legend text: 10px / 12px
- Custom legend overlays: 10px / 12px

**Color Usage:**
- **Primary differentiation**: Color distinguishes different entities (XD segments, signals, etc.)
- **Secondary differentiation**: Line style distinguishes time periods/types within same entity
- **Colorblind support**: All charts respect `themeStore.colorblindMode` flag, using scientifically validated palettes (Wong 2011 / IBM Design / Okabe Ito)
- **Standard palettes**: Defined consistently across all chart components (light mode, dark mode, colorblind variants)

**Grid Layout (Mobile / Desktop):**
- Left margin: 60px / 80px
- Right margin: 20px / 50px (no legend), 20px / 200px (with legend)
- Bottom margin: 70px / 60px
- Top margin: Varies by chart (80-120px) to accommodate titles and custom legends

**Axis Formatting:**
- **Time-of-day mode**: Format as `HH:MM` (e.g., "14:30")
- **Date/time mode**: Show day-of-week at midnight, otherwise just time (e.g., "Mon 01/15\n00:00" or "14:30")
- **Y-axis precision**: Dynamic based on data range (0.05, 0.1, 0.2, or 0.5 intervals)

**Entity Limits:**
- **Main charts** (TravelTime, Anomalies, BeforeAfter): 6-10 entities (configurable via `maxLegendEntities`)
- **Small multiples**: 12 entities (2 columns × 6 rows, hard limit)
- **Warning display**: Shows at `displayedCount === limit` using v-alert with `compact` density, `outlined` variant, `orange-darken-2` color

**Legend Patterns:**
- **Standard mode**: Show all series names (one color per series)
- **Deduplicated mode** (Anomalies forecast, BeforeAfter with groups): Show unique entity names only, use custom graphic overlay to explain line types
- **Custom legend overlay**: Positioned top-center, shows line type meanings (e.g., "After" solid, "Before" dashed)

**When Adding New Chart Pages:**
1. Import and use `useThemeStore` for colorblind mode support
2. Implement responsive font sizes using `isMobile` detection (`window.innerWidth < 600`)
3. Use standard color palettes (lightModePalette, darkModePalette, colorblind variants)
4. Follow line type convention (solid=primary, dashed=secondary)
5. Add warning display when entity limit reached (trigger at `===` limit)
6. Ensure axis formatting matches existing patterns (time-of-day, date/time)
7. Use consistent grid margins and spacing

### Styling Consistency

- Treat new views (e.g., the Changepoints page) as peers to existing pages—reuse the shared layout patterns, Vuetify components, and theme-aware color scales so the app feels cohesive.
- Map legends, filters, and selection states should mirror established UX (signal chips, selection counters, auto-zoom behavior).
- When introducing a new visualization or interaction, cross-check TravelTime, Anomalies, and BeforeAfter implementations to keep typography, spacing, and iconography aligned.

## Database Schema

Full schema definitions are in README.md reference when needed.



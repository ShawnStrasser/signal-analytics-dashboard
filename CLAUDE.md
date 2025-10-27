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
  - `BeforeAfter.vue` - Scrollable layout with map, before/after comparison chart, and small multiples chart (2-column grid, max 10 entities)
- **Components**: `frontend/src/components/`
  - `SharedMap.vue` - Leaflet map component supporting 'travel-time', 'anomaly', and 'before-after' data types
  - `FilterPanel.vue` - Filter controls with conditional date selectors (standard dates or BeforeAfterDateSelector based on route)
  - `BeforeAfterDateSelector.vue` - Dual date range selectors with color-coded styling (blue for before, orange for after)
  - `TravelTimeChart.vue` - ECharts time series visualization
  - `AnomalyChart.vue` - ECharts dual-series chart with anomaly highlighting
  - `BeforeAfterChart.vue` - ECharts chart with hard-coded before/after legend (no dropdown)
  - `SmallMultiplesChart.vue` - ECharts small multiples grid (2 columns, up to 5 rows, shared axes)

### Key Design Patterns
1. **Two-stage querying**: API endpoints first query `DIM_SIGNALS_XD` to resolve signal IDs → XD segments, then query `TRAVEL_TIME_ANALYTICS` with XD filters
2. **XD-based filtering**: Map interactions pass XD segment IDs directly to avoid repeated dimension table lookups
3. **Arrow data flow**: Backend streams Arrow data → Frontend deserializes with `apache-arrow` library
4. **Shared state**: Pinia stores enable filter persistence when switching between pages
5. **Responsive layout**: CSS Grid with flexbox for dynamic height management; Travel Time and Anomalies use no scrolling, Before/After allows scrolling
6. **Before/After comparison**: CTE-based SQL queries calculate TTI for before and after periods separately, then join/union results with PERIOD column
7. **Remove anomalies filter**: Available on Travel Time and Before/After pages, adds `WHERE IS_ANOMALY = FALSE` to backend queries
8. **Color scales**: Shared color scheme (green→yellow→orange→red) with different mappings: TTI (1.0-3.0), Anomaly % (0-10%), Before/After difference (-0.25 to +0.25)

## Database Schema

Full schema definitions are in README.md reference when needed.



# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a full-stack traffic signal analytics dashboard that visualizes travel time data and anomalies. The backend is a Flask REST API that serves Apache Arrow data directly from Snowflake, while the frontend is a Vue.js 3 SPA with Vuetify UI components.

## Claude Code Workflow

IMPORTANT! At start of new chat, commit all previous changes! Do this before making any modifications. Use a simple, concise commit message (one sentence or less) that briefly describes the changes. Do not include Claude Code signatures or co-authorship attributions. Do not commit .md files that are just developer notes or instructions. Continue to make commits during the conversation as needed, and use git to revert changes if needed.

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
  - `api_travel_time.py` - Travel time data endpoints (summary, aggregated, time-of-day)
  - `api_anomalies.py` - Anomaly analysis endpoints
- **Data format**: All API responses return Apache Arrow IPC streams (`application/octet-stream`) for efficient data transfer

### Frontend (Vue.js 3 + Vuetify)
- **Entry point**: `frontend/src/main.js` - Initializes Vue app with Pinia, Vue Router, and Vuetify
- **Router**: `frontend/src/router.js` - Two main routes: `/travel-time` and `/anomalies`
- **State management**: Pinia stores in `frontend/src/stores/`:
  - `filters.js` - Date range, signal selection, approach/geometry filters, day-of-week filter, time-of-day filter (shared across pages)
  - `selection.js` - Selected XD segments from map interactions
  - `mapState.js` - Map view state persistence
  - `geometry.js` - Cached XD road segment geometries (GeoJSON)
- **Views**: `frontend/src/views/`
  - `TravelTime.vue` - Map + time series chart for travel time analysis with optional time-of-day aggregation
  - `Anomalies.vue` - Map + dual-series chart comparing actual vs predicted travel times
- **Components**: `frontend/src/components/`
  - `SharedMap.vue` - Leaflet map component used by both views
  - `FilterPanel.vue` - Filter controls for date range and signal selection
  - `TravelTimeChart.vue` - ECharts time series visualization
  - `AnomalyChart.vue` - ECharts dual-series chart with anomaly highlighting

### Key Design Patterns
1. **Two-stage querying**: API endpoints first query `DIM_SIGNALS_XD` to resolve signal IDs → XD segments, then query `TRAVEL_TIME_ANALYTICS` with XD filters
2. **XD-based filtering**: Map interactions pass XD segment IDs directly to avoid repeated dimension table lookups
3. **Arrow data flow**: Backend streams Arrow data → Frontend deserializes with `apache-arrow` library
4. **Shared state**: Pinia stores enable filter persistence when switching between Travel Time and Anomalies pages

## Database Schema

### Tables
- **DIM_SIGNALS_XD**: Signal dimension table with XD segments, lat/lon, approach/extended flags, valid_geometry
- **TRAVEL_TIME_ANALYTICS**: Time series data with XD, timestamp, travel_time_seconds, prediction, anomaly flags, TIME_15MIN (computed as TO_TIME(TIMESTAMP))
- **DIM_DATE**: Date dimension table with DATE_ONLY and DAY_OF_WEEK_ISO (1=Mon, 7=Sun)
- **XD_GEOM**: Road segment geometries (ST_ASGEOJSON format) keyed by XD
- **CHANGEPOINTS**: Detected changepoints with scores and before/after averages
- **FREEFLOW**: Free-flow travel times by XD segment

Full schema definitions are in README.md.


## Important Notes

- **Arrow serialization**: Use `pyarrow.ipc.new_stream()` to serialize Arrow tables, not `to_pybytes()` directly
- **Date normalization**: All API endpoints normalize dates to `YYYY-MM-DD` format using `pd.to_datetime().strftime()`
- **Empty results**: API endpoints return empty Arrow tables with proper schema when no data matches filters
- **XD caching**: `xd-geometry` endpoint caches GeoJSON data in `_xd_geometry_cache` global variable
- **Filter persistence**: All filter state persists in Pinia stores when navigating between pages


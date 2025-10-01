# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a full-stack traffic signal analytics dashboard that visualizes travel time data and anomalies. The backend is a Flask REST API that serves Apache Arrow data directly from Snowflake, while the frontend is a Vue.js 3 SPA with Vuetify UI components.

## Architecture

### Backend (Flask + Snowflake)
- **Entry point**: `app.py` - Flask application that registers API blueprints and serves the Vue.js frontend
- **Database connection**: `database.py` - Manages Snowflake session with two connection methods:
  1. Active session (preferred): Uses `get_active_session()` from `snowflake.snowpark.context`
  2. Connection parameters: Reads `SNOWFLAKE_CONNECTION` environment variable
- **API routes**: Organized as Flask blueprints in `routes/`:
  - `api_travel_time.py` - Travel time data endpoints
  - `api_anomalies.py` - Anomaly analysis endpoints
- **Data format**: All API responses return Apache Arrow IPC streams (`application/octet-stream`) for efficient data transfer

### Frontend (Vue.js 3 + Vuetify)
- **Entry point**: `frontend/src/main.js` - Initializes Vue app with Pinia, Vue Router, and Vuetify
- **Router**: `frontend/src/router.js` - Two main routes: `/travel-time` and `/anomalies`
- **State management**: Pinia stores in `frontend/src/stores/`:
  - `filters.js` - Date range, signal selection, approach/geometry filters (shared across pages)
  - `selection.js` - Selected XD segments from map interactions
  - `mapState.js` - Map view state persistence
  - `geometry.js` - Cached XD road segment geometries (GeoJSON)
- **Views**: `frontend/src/views/`
  - `TravelTime.vue` - Map + time series chart for travel time analysis
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
- **TRAVEL_TIME_ANALYTICS**: Time series data with XD, timestamp, travel_time_seconds, prediction, anomaly flags
- **XD_GEOM**: Road segment geometries (ST_ASGEOJSON format) keyed by XD
- **CHANGEPOINTS**: Detected changepoints with scores and before/after averages
- **FREEFLOW**: Free-flow travel times by XD segment

Full schema definitions are in README.md.

## Development Commands

### Backend
```bash
# Install Python dependencies
pip install -r requirements.txt

# Run Flask development server (localhost:5000)
python app.py
```

### Frontend
```bash
# Navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# Run Vite development server with proxy to Flask (localhost:5173)
npm run dev

# Build production bundle (outputs to ../static/dist)
npm run build

# Preview production build
npm run preview
```

### Environment Setup
Set Snowflake connection using one of these methods:
1. **Active session** (preferred): Ensure active Snowflake session exists
2. **Environment variable**:
   ```bash
   export SNOWFLAKE_CONNECTION='{"account":"...","user":"...","password":"...","warehouse":"...","database":"...","schema":"..."}'
   ```

## Development Workflow

1. **Frontend development**: Run `npm run dev` in `frontend/` directory, which proxies `/api` calls to Flask backend
2. **Backend development**: Run `python app.py` in root directory
3. **Production deployment**: Run `npm run build` to bundle frontend, then run Flask app which serves from `static/dist`

## Important Notes

- **Arrow serialization**: Use `pyarrow.ipc.new_stream()` to serialize Arrow tables, not `to_pybytes()` directly
- **Date normalization**: All API endpoints normalize dates to `YYYY-MM-DD` format using `pd.to_datetime().strftime()`
- **Empty results**: API endpoints return empty Arrow tables with proper schema when no data matches filters
- **XD caching**: `xd-geometry` endpoint caches GeoJSON data in `_xd_geometry_cache` global variable
- **Filter persistence**: All filter state persists in Pinia stores when navigating between pages

## Claude Code Workflow

**At the start of every new conversation**: Commit all current changes before making any modifications. Use a simple, concise commit message (one sentence or less) that briefly describes the changes. Do not include Claude Code signatures or co-authorship attributions.
# Signal Analytics Dashboard
Flask API plus Vue.js frontend for visualizing travel time analytics from Snowflake and emailing monitoring reports.

DISCLAIMER: This README was AI generated.

## What's inside
- Flask backend in `app.py` serving `/api` endpoints defined under `routes/` and static assets from `static/dist`.
- Snowflake access via Snowpark (`database.py`) with Arrow IPC responses; uses an active session when available or `SNOWFLAKE_CONNECTION` credentials.
- Vue 3 + Vite + Vuetify + ECharts + Leaflet UI in `frontend/`, built into `static/dist` (Vite dev server proxies `/api` to `localhost:5000`).
- Email-based authentication and monitoring subscriptions persisted in SQLite (`services/subscription_store.py`), with Brevo sending login links and PDF reports from `services/report_service.py`.
- APScheduler dispatches daily monitoring reports when `ENABLE_DAILY_REPORTS` is enabled.

## Requirements
- Python with pip (dependencies in `requirements.txt`).
- Node.js and npm for building the frontend.
- Snowflake credentials: either an active Snowpark session or `SNOWFLAKE_CONNECTION='{\"account\":\"...\",\"user\":\"...\",\"password\":\"...\",\"warehouse\":\"...\",\"database\":\"...\",\"schema\":\"...\"}'`.
- `SECRET_KEY` for Flask sessions.
- Brevo credentials for email features: `BREVO_API_KEY` and optional `EMAIL_SENDER_EMAIL`/`BREVO_SENDER_EMAIL`; TLS verification can be relaxed with `BREVO_DISABLE_SSL_VERIFY=true`.
- Optional configuration: `PUBLIC_BASE_URL` for magic links, `SUBSCRIPTION_DB_PATH` for the SQLite file (defaults to `/data/subscriptions.db` when `/data` exists, otherwise the project root), `TIMEZONE`, `ENABLE_DAILY_REPORTS`, `ANOMALY_MONITORING_THRESHOLD`, `CHANGEPOINT_SEVERITY_THRESHOLD`.

## Backend setup
1) Create and activate a virtual environment.  
2) Install dependencies: `pip install -r requirements.txt`.  
3) Export Snowflake credentials (`SNOWFLAKE_CONNECTION` if no active session) and `SECRET_KEY`.  
4) Set Brevo variables if you need to send emails.

## Running
- API (dev): `python app.py` - serves `http://localhost:5000`, starts the scheduler (unless `ENABLE_DAILY_REPORTS` is false), and serves `static/dist`.
- API (prod): `gunicorn --bind 0.0.0.0:$PORT app:app` (see `Procfile`).
- Frontend (dev): `cd frontend && npm install && npm run dev` - Vite proxies API calls to the Flask server.
- Frontend build for Flask: `cd frontend && npm run build` - outputs to `static/dist` consumed by `app.py`.

## Tests
- Backend: `pytest`
- Frontend: `cd frontend && npm test` (Vitest)

## Repository layout
- `app.py` - Flask entry point, static file serving, scheduler startup.
- `routes/` - API blueprints for travel time, anomalies, before/after, changepoints, auth, subscriptions, captcha, and admin utilities.
- `services/` - report generation, Brevo email sending, subscription storage, scheduler, rate limiting, and captcha session helpers.
- `frontend/` - Vue/Vuetify source (built via Vite) with output in `static/dist`.
- `tests/` - backend tests and schema fixtures.

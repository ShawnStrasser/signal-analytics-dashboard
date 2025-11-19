"""
Flask Backend for Signal Analytics Dashboard
Serves Arrow data directly from Snowflake
"""

import os
import sys
import pyarrow as pa
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from database import get_snowflake_session, get_connection_status
from routes.api_auth import auth_bp
from routes.api_before_after import before_after_bp
from routes.api_anomalies import anomalies_bp
from routes.api_changepoints import changepoints_bp
from routes.api_travel_time import travel_time_bp
from routes.api_subscriptions import subscriptions_bp
from routes.api_captcha import captcha_bp
from services import subscription_store
from services.scheduler import start_scheduler
from services.rate_limiter import rate_limiter
from services import captcha_sessions
from config import SECRET_KEY

# Download timezone database on Windows if needed
if sys.platform == 'win32':
    try:
        pa.util.download_tzdata_on_windows()
        print("✅ Timezone database downloaded")
    except Exception as e:
        print(f"⚠️  Failed to download timezone database: {e}")

app = Flask(__name__, static_folder='static/dist')
app.config['SECRET_KEY'] = SECRET_KEY
CORS(app)

subscription_store.initialize()

if os.environ.get("PYTEST_CURRENT_TEST") is None:
    start_scheduler()

GENERAL_RATE_LIMITS = [
    ("minute", 120, 60),
    ("hour", 2000, 3600),
]
GENERAL_RATE_LIMIT_ENDPOINT_EXEMPTIONS = {"health_check", "connection_status"}
GENERAL_RATE_LIMIT_PATH_PREFIX_EXEMPTIONS = ("/static/", "/favicon.ico")


def _get_client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


@app.before_request
def apply_global_rate_limit():
    if request.method == "OPTIONS":
        return None

    endpoint = request.endpoint or ""
    if endpoint in GENERAL_RATE_LIMIT_ENDPOINT_EXEMPTIONS:
        return None

    path = request.path or ""
    if any(path.startswith(prefix) for prefix in GENERAL_RATE_LIMIT_PATH_PREFIX_EXEMPTIONS):
        return None

    client_ip = _get_client_ip()
    for name, limit, window in GENERAL_RATE_LIMITS:
        key = f"rate:{name}:{client_ip}"
        allowed, retry_after = rate_limiter.allow(key, limit, window)
        if not allowed:
            wait_seconds = max(1, int(retry_after or window))
            response = jsonify({"error": "Too many requests. Please slow down."})
            response.headers["Retry-After"] = str(wait_seconds)
            return response, 429

    return None

@app.route('/api/health')
def health_check():
    """Health check endpoint with connection status"""
    status = get_connection_status()
    session = get_snowflake_session()
    return jsonify({
        'status': 'healthy' if session else 'unhealthy',
        'database_connected': session is not None,
        'connecting': status['connecting'],
        'error': status['error']
    })

@app.route('/api/connection-status')
def connection_status():
    """Get detailed connection status"""
    status = get_connection_status()
    return jsonify(status)

@app.route('/api/config')
def get_config():
    """Get frontend configuration values"""
    from config import (
        MAX_LEGEND_ENTITIES,
        MAX_ANOMALY_LEGEND_ENTITIES,
        MAX_BEFORE_AFTER_LEGEND_ENTITIES,
        DEFAULT_START_HOUR,
        DEFAULT_END_HOUR,
        ANOMALY_MONITORING_THRESHOLD,
        CHANGEPOINT_SEVERITY_THRESHOLD,
    )
    return jsonify({
        'maxLegendEntities': MAX_LEGEND_ENTITIES,
        'maxAnomalyLegendEntities': MAX_ANOMALY_LEGEND_ENTITIES,
        'maxBeforeAfterLegendEntities': MAX_BEFORE_AFTER_LEGEND_ENTITIES,
        'defaultStartHour': DEFAULT_START_HOUR,
        'defaultEndHour': DEFAULT_END_HOUR,
        'anomalyMonitoringThreshold': ANOMALY_MONITORING_THRESHOLD,
        'changepointSeverityThreshold': CHANGEPOINT_SEVERITY_THRESHOLD,
    })

# Register blueprints
app.register_blueprint(travel_time_bp, url_prefix='/api')
app.register_blueprint(anomalies_bp, url_prefix='/api')
app.register_blueprint(before_after_bp, url_prefix='/api')
app.register_blueprint(changepoints_bp, url_prefix='/api')
app.register_blueprint(auth_bp, url_prefix='/api')
app.register_blueprint(subscriptions_bp, url_prefix='/api')
app.register_blueprint(captcha_bp, url_prefix='/api')

CAPTCHA_EXEMPT_PATHS = (
    "/api/captcha",
    "/api/health",
)


@app.before_request
def enforce_captcha_verification():
    if request.method == "OPTIONS":
        return None
    path = request.path or ""
    if not path.startswith("/api/"):
        return None
    for exempt in CAPTCHA_EXEMPT_PATHS:
        if path.startswith(exempt):
            return None
    if captcha_sessions.is_verified(request):
        return None
    return jsonify({"error": "captcha_required"}), 401

# Serve Vue.js app in production
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_vue_app(path):
    """Serve Vue.js application"""
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    # Warm up database connection on startup
    print("🔄 Warming up database connection...")
    session = get_snowflake_session(retry=True, max_retries=3, retry_delay=2)
    if session:
        print("✅ Database connection established")
    else:
        print("⚠️  Database connection failed - will retry on first request")

    app.run(debug=True, host='127.0.0.1', port=5000)

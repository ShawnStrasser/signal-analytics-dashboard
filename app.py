"""
Flask Backend for Signal Analytics Dashboard
Serves Arrow data directly from Snowflake
"""

import os
import sys
import pyarrow as pa
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_compress import Compress
from database import get_snowflake_session, get_connection_status

# Download timezone database on Windows if needed
if sys.platform == 'win32':
    try:
        pa.util.download_tzdata_on_windows()
        print("✅ Timezone database downloaded")
    except Exception as e:
        print(f"⚠️  Failed to download timezone database: {e}")

app = Flask(__name__, static_folder='frontend/dist')
CORS(app)

# Enable gzip/brotli compression for all responses
# Configure for minimum size threshold to avoid compressing small responses
app.config['COMPRESS_MIMETYPES'] = [
    'text/html', 'text/css', 'text/xml',
    'application/json', 'application/javascript',
    'application/octet-stream'  # Include Arrow binary data
]
app.config['COMPRESS_MIN_SIZE'] = 500  # Only compress responses > 500 bytes
app.config['COMPRESS_LEVEL'] = 6  # Balance between speed and compression ratio
Compress(app)

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
    from config import MAX_LEGEND_ENTITIES, DEFAULT_START_HOUR, DEFAULT_END_HOUR
    return jsonify({
        'maxLegendEntities': MAX_LEGEND_ENTITIES,
        'defaultStartHour': DEFAULT_START_HOUR,
        'defaultEndHour': DEFAULT_END_HOUR
    })

# Import route modules
from routes.api_travel_time import travel_time_bp
from routes.api_anomalies import anomalies_bp

# Register blueprints
app.register_blueprint(travel_time_bp, url_prefix='/api')
app.register_blueprint(anomalies_bp, url_prefix='/api')

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

    app.run(debug=True, host='0.0.0.0', port=5000)
"""
Flask Backend for Signal Analytics Dashboard
Serves Arrow data directly from Snowflake
"""

import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from database import get_snowflake_session

app = Flask(__name__, static_folder='frontend/dist')
CORS(app)

@app.route('/api/health')
def health_check():
    """Health check endpoint"""
    session = get_snowflake_session()
    return jsonify({
        'status': 'healthy' if session else 'unhealthy',
        'snowflake_connected': session is not None
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
    app.run(debug=True, host='0.0.0.0', port=5000)
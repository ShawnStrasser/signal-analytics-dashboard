"""
Application Configuration
Controls debugging, caching, and performance logging
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


# =============================================================================
# DEBUG SETTINGS
# =============================================================================

# Enable/disable performance timing logs in backend
DEBUG_BACKEND_TIMING = False

# Enable/disable Snowflake query result caching
# When False, adds ALTER SESSION SET USE_CACHED_RESULT = FALSE
DEBUG_DISABLE_SNOWFLAKE_CACHE = False

# Enable/disable server-side result caching (geometry cache, etc.)
DEBUG_DISABLE_SERVER_CACHE = False

# =============================================================================
# FRONTEND DEBUG SETTINGS (referenced in API responses)
# =============================================================================

# Enable/disable verbose console logging in frontend
# This can be read by frontend via a /config endpoint if needed
DEBUG_FRONTEND_LOGGING = True

# =============================================================================
# TIMEZONE SETTINGS
# =============================================================================

# Timezone for timestamp data stored in Snowflake
# Data in Snowflake is stored without timezone (local time)
# This setting tells Arrow how to interpret those timestamps
# Examples: 'America/Los_Angeles', 'America/Denver', 'America/Chicago', 'America/New_York'
TIMEZONE = 'America/Los_Angeles'

# =============================================================================
# CHART SETTINGS
# =============================================================================

# Maximum number of entities to display in chart legends
# Prevents overwhelming charts with too many series
# Applies to legend grouping by: XD, BEARING, COUNTY, ROADNAME, ID
MAX_LEGEND_ENTITIES = 10

# Maximum number of entities for Anomaly charts (reduced because each entity has 2 lines)
MAX_ANOMALY_LEGEND_ENTITIES = 6

# Maximum number of entities for Before/After main chart (reduced because each entity has 2 lines)
MAX_BEFORE_AFTER_LEGEND_ENTITIES = 6

# Maximum number of entities for Before/After Small Multiples chart
# Higher limit because each entity gets its own mini-chart (2 columns x 6 rows = 12)
MAX_BEFORE_AFTER_SMALL_MULTIPLES_ENTITIES = 12

# =============================================================================
# MONITORING SETTINGS
# =============================================================================

# Threshold applied to anomaly monitoring score when selecting segments
ANOMALY_MONITORING_THRESHOLD = 4.0

# Threshold applied to changepoint severity score before surfacing results
CHANGEPOINT_SEVERITY_THRESHOLD = 30.0

# =============================================================================
# TIME OF DAY FILTER SETTINGS
# =============================================================================

# Default time range for time-of-day filter
# Data collection window (24-hour format)
DEFAULT_START_HOUR = 6   # 06:00
DEFAULT_END_HOUR = 19    # 19:00

# =============================================================================
# CORE SECURITY SETTINGS
# =============================================================================

SECRET_KEY = os.environ.get('SECRET_KEY')
CLIENT_ID_COOKIE_NAME = 'signal_client_id'
CLIENT_ID_TOKEN_BYTES = 32
CLIENT_ID_COOKIE_MAX_AGE = 365 * 24 * 60 * 60

# =============================================================================
# SUBSCRIPTION & AUTH SETTINGS
# =============================================================================

def _default_subscription_path() -> str:
    data_dir = Path('/data')
    if data_dir.is_dir():
        return str(data_dir / 'subscriptions.db')
    return str(BASE_DIR / 'subscriptions.db')


SUBSCRIPTION_DB_PATH = os.environ.get(
    'SUBSCRIPTION_DB_PATH',
    _default_subscription_path()
)

LOGIN_TOKEN_TTL_MINUTES = 60
SESSION_TTL_DAYS = None

PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL')

# =============================================================================
# EMAIL SETTINGS
# =============================================================================

BREVO_API_KEY = os.environ.get('BREVO_API_KEY')
BREVO_DISABLE_SSL_VERIFY = os.environ.get('BREVO_DISABLE_SSL_VERIFY', 'false').lower() == 'true'

EMAIL_SENDER_ADDRESS = os.environ.get('EMAIL_SENDER_EMAIL', os.environ.get('BREVO_SENDER_EMAIL', 'no-reply@example.com'))
EMAIL_SENDER_NAME = "Signal Analytics Reports"

# =============================================================================
# SCHEDULER SETTINGS
# =============================================================================

ENABLE_DAILY_REPORTS = True
DAILY_REPORT_SEND_HOUR = 6
DAILY_REPORT_SEND_MINUTE = 0

# =============================================================================
# DEVELOPMENT HELPERS
# =============================================================================

DEBUG_SAVE_REPORT_PDF = False

# =============================================================================
# PRODUCTION SETTINGS
# =============================================================================

# In production, set all DEBUG flags to False for minimal logging
# Only critical errors and warnings will be logged

PRODUCTION_MODE = os.environ.get('APP_PRODUCTION_MODE', 'false').lower() == 'true'

if PRODUCTION_MODE:
    DEBUG_BACKEND_TIMING = False
    DEBUG_DISABLE_SNOWFLAKE_CACHE = False
    DEBUG_DISABLE_SERVER_CACHE = False
    DEBUG_FRONTEND_LOGGING = False

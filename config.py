"""
Application Configuration
Controls debugging, caching, and performance logging
"""

# =============================================================================
# DEBUG SETTINGS
# =============================================================================

# Enable/disable performance timing logs in backend
DEBUG_BACKEND_TIMING = True

# Enable/disable Snowflake query result caching
# When False, adds ALTER SESSION SET USE_CACHED_RESULT = FALSE
DEBUG_DISABLE_SNOWFLAKE_CACHE = True

# Enable/disable server-side result caching (geometry cache, etc.)
DEBUG_DISABLE_SERVER_CACHE = True

# =============================================================================
# FRONTEND DEBUG SETTINGS (referenced in API responses)
# =============================================================================

# Enable/disable verbose console logging in frontend
# This can be read by frontend via a /config endpoint if needed
DEBUG_FRONTEND_LOGGING = True

# =============================================================================
# PRODUCTION SETTINGS
# =============================================================================

# In production, set all DEBUG flags to False for minimal logging
# Only critical errors and warnings will be logged

PRODUCTION_MODE = False  # Set to True in production deployment

if PRODUCTION_MODE:
    DEBUG_BACKEND_TIMING = False
    DEBUG_DISABLE_SNOWFLAKE_CACHE = False
    DEBUG_DISABLE_SERVER_CACHE = False
    DEBUG_FRONTEND_LOGGING = False

"""
Database connection utilities for Snowflake
"""

import os
import json
import time
from snowflake.snowpark.session import Session

# Global session variable
snowflake_session = None
connection_status = {'connected': False, 'connecting': False, 'error': None}
_cache_disabled = False  # Track if we've already disabled cache this session

def get_connection_status():
    """Get current connection status"""
    return connection_status.copy()

def get_snowflake_session(retry=False, max_retries=3, retry_delay=2):
    """Get or create Snowflake session with retry logic"""
    global snowflake_session, connection_status, _cache_disabled

    from config import DEBUG_DISABLE_SNOWFLAKE_CACHE

    # Return existing session if valid
    if snowflake_session is not None:
        try:
            # Don't run health check every time - too many queries!
            # Just return the session, errors will surface on actual queries
            connection_status['connected'] = True
            connection_status['error'] = None
            return snowflake_session
        except:
            # Session is invalid, will recreate
            snowflake_session = None
            connection_status['connected'] = False
            _cache_disabled = False

    # If already connecting (from another thread), wait briefly
    if connection_status['connecting'] and not retry:
        time.sleep(1)
        if snowflake_session is not None:
            return snowflake_session

    connection_status['connecting'] = True
    attempts = max_retries if retry else 1

    for attempt in range(attempts):
        try:
            # Import here to defer the warning until actual use
            from snowflake.snowpark.context import get_active_session

            # Try to get active session first
            print(f"Attempting to connect to database (attempt {attempt + 1}/{attempts})...")
            snowflake_session = get_active_session()
            print("Connected using active session")
            connection_status['connected'] = True
            connection_status['connecting'] = False
            connection_status['error'] = None

            # Disable Snowflake query result cache if configured (ONCE per session)
            from config import DEBUG_DISABLE_SNOWFLAKE_CACHE
            if DEBUG_DISABLE_SNOWFLAKE_CACHE and not _cache_disabled:
                snowflake_session.sql("ALTER SESSION SET USE_CACHED_RESULT = FALSE").collect()
                print("Snowflake query result cache DISABLED")
                _cache_disabled = True

            return snowflake_session
        except Exception as e:
            # Only print if it's not the expected "No default Session" error
            if "No default Session is found" not in str(e):
                print(f"Active session not available: {e}")

            try:
                # Fallback to connection parameters
                connection_parameters = json.loads(os.environ.get("SNOWFLAKE_CONNECTION", "{}"))

                if not connection_parameters:
                    raise Exception("No Snowflake connection parameters found")

                snowflake_session = Session.builder.configs(connection_parameters).create()
                print("Connected using connection parameters")
                connection_status['connected'] = True
                connection_status['connecting'] = False
                connection_status['error'] = None

                # Disable Snowflake query result cache if configured (ONCE per session)
                from config import DEBUG_DISABLE_SNOWFLAKE_CACHE
                if DEBUG_DISABLE_SNOWFLAKE_CACHE and not _cache_disabled:
                    snowflake_session.sql("ALTER SESSION SET USE_CACHED_RESULT = FALSE").collect()
                    print("Snowflake query result cache DISABLED")
                    _cache_disabled = True

                return snowflake_session

            except Exception as e:
                error_msg = f"Failed to connect to database: {e}"
                print(error_msg)
                connection_status['error'] = str(e)

                # Retry if requested and not the last attempt
                if retry and attempt < attempts - 1:
                    print(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                    continue

                connection_status['connecting'] = False
                return None

    connection_status['connecting'] = False
    return None
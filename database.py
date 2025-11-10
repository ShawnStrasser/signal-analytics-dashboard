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
_force_new_session = False  # Flag to force creating new session instead of using get_active_session()

def get_connection_status():
    """Get current connection status"""
    return connection_status.copy()

def is_auth_error(error):
    """Check if error is an authentication/session error that requires reconnection"""
    error_str = str(error).lower()
    # Check for various session/auth error patterns:
    # - authentication token has expired
    # - 08001: connection error code
    # - 390111: session no longer exists error
    # - session no longer exists
    # - new login required
    return (
        'authentication token has expired' in error_str or
        '08001' in error_str or
        '390111' in error_str or
        'session no longer exists' in error_str or
        'new login required' in error_str
    )

def invalidate_session():
    """Invalidate the current session to force reconnection"""
    global snowflake_session, connection_status, _cache_disabled, _force_new_session

    # Try to close the existing session if it exists
    # Note: If the session is already dead (expired/terminated), close() will fail - this is expected
    if snowflake_session is not None:
        try:
            snowflake_session.close()
            print("🔄 Closed existing Snowflake session")
        except Exception:
            # Expected - session is already dead, nothing to close
            pass

    snowflake_session = None
    connection_status['connected'] = False
    connection_status['error'] = None
    _cache_disabled = False
    _force_new_session = True  # Force creation of new session on next connection
    print("🔄 Session invalidated - will create new session on next query")

def get_snowflake_session(retry=False, max_retries=3, retry_delay=2):
    """Get or create Snowflake session with retry logic"""
    global snowflake_session, connection_status, _cache_disabled, _force_new_session

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
        # If _force_new_session is True, skip get_active_session and go directly to connection parameters
        if not _force_new_session:
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
                # Fall through to connection parameters below

        # Use connection parameters (either because _force_new_session or get_active_session failed)
        try:
            if _force_new_session:
                print(f"🔄 Creating new session with connection parameters (attempt {attempt + 1}/{attempts})...")

            # Fallback to connection parameters
            raw_conn = os.environ.get("SNOWFLAKE_CONNECTION")
            if not raw_conn:
                raise Exception("SNOWFLAKE_CONNECTION environment variable must be set")
            connection_parameters = json.loads(raw_conn)
            if not connection_parameters:
                raise Exception("SNOWFLAKE_CONNECTION environment variable is empty")

            snowflake_session = Session.builder.configs(connection_parameters).create()
            print("✅ Connected using connection parameters")
            connection_status['connected'] = True
            connection_status['connecting'] = False
            connection_status['error'] = None
            _force_new_session = False  # Reset flag after successful connection

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

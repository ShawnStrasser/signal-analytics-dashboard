"""
Error handling utilities for API routes
Handles authentication token expiry and session reconnection
"""

import time
from database import is_auth_error, invalidate_session, get_snowflake_session

def handle_auth_error_retry(query_func, max_retries=2):
    """
    Execute a query function with automatic retry on authentication errors

    Args:
        query_func: Function that executes the query and returns the result
        max_retries: Maximum number of retries (default 2)

    Returns:
        Query result on success

    Raises:
        Exception if query fails after all retries
    """
    for attempt in range(max_retries + 1):
        try:
            # Execute the query
            result = query_func()
            return result

        except Exception as e:
            # Check if this is an authentication error
            if is_auth_error(e):
                print(f"🔐 Authentication error detected (attempt {attempt + 1}/{max_retries + 1}): {e}")

                # If we have retries left, invalidate session and try again
                if attempt < max_retries:
                    print("🔄 Invalidating session and retrying...")
                    invalidate_session()

                    # Get a new session (with built-in retry logic)
                    new_session = get_snowflake_session(retry=True, max_retries=3, retry_delay=2)
                    if not new_session:
                        raise Exception("Failed to reconnect to database after authentication error")

                    # Small delay before retry to ensure session is fully established
                    time.sleep(0.5)
                    continue
                else:
                    # Out of retries
                    print(f"❌ Authentication error persists after {max_retries + 1} attempts")
                    raise
            else:
                # Not an auth error, re-raise immediately
                raise

    # Should never reach here, but just in case
    raise Exception("Query failed after all retry attempts")

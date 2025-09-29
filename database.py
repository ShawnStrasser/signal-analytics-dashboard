"""
Database connection utilities for Snowflake
"""

import os
import json
from snowflake.snowpark.session import Session

# Global session variable
snowflake_session = None

def get_snowflake_session():
    """Get or create Snowflake session"""
    global snowflake_session
    
    # Return existing session if valid
    if snowflake_session is not None:
        try:
            # Test if session is still valid by running a simple query
            snowflake_session.sql("SELECT 1").collect()
            return snowflake_session
        except:
            # Session is invalid, will recreate
            snowflake_session = None
    
    try:
        # Import here to defer the warning until actual use
        from snowflake.snowpark.context import get_active_session
        
        # Try to get active session first
        snowflake_session = get_active_session()
        print("Connected using active Snowflake session")
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
            return snowflake_session
            
        except Exception as e:
            print(f"Failed to connect to Snowflake: {e}")
            return None
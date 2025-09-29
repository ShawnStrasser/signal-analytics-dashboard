"""
Database connection utilities for Snowflake
"""

import os
import json
from snowflake.snowpark.session import Session
from snowflake.snowpark.context import get_active_session

# Global session variable
snowflake_session = None

def get_snowflake_session():
    """Get or create Snowflake session"""
    global snowflake_session
    
    if snowflake_session is not None:
        return snowflake_session
    
    try:
        # Try to get active session first
        snowflake_session = get_active_session()
        print("Connected using active Snowflake session")
        return snowflake_session
    except Exception as e:
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
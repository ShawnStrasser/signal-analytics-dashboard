"""
Database connection utilities for Snowflake.
"""

import os
import json
import streamlit as st
from snowflake.snowpark.session import Session
from snowflake.snowpark.context import get_active_session
import pandas as pd


@st.cache_resource
def get_snowflake_session():
    """
    Get Snowflake session using active session first, then fallback to connection params.
    """
    try:
        # Try to get active session first (preferred method)
        session = get_active_session()
        st.success("Connected using active Snowflake session")
        return session
    except Exception as e:
        st.info(f"Active session not available: {e}")
        
        try:
            # Fallback to connection parameters from environment
            connection_parameters = json.loads(os.environ.get("SNOWFLAKE_CONNECTION", "{}"))
            
            if not connection_parameters:
                st.error("No Snowflake connection parameters found in SNOWFLAKE_CONNECTION environment variable")
                return None
            
            session = Session.builder.configs(connection_parameters).create()
            st.success("Connected using connection parameters")
            return session
            
        except Exception as e:
            st.error(f"Failed to connect to Snowflake: {e}")
            return None


@st.cache_data
def get_signals_data(_session):
    """
    Get signals dimension data with caching.
    """
    if _session is None:
        return pd.DataFrame()
    
    query = """
    SELECT 
        ID,
        LATITUDE,
        LONGITUDE,
        VALID_GEOMETRY,
        XD,
        BEARING,
        COUNTY,
        ROADNAME,
        MILES,
        APPROACH,
        EXTENDED
    FROM TPAU_DB.TPAU_RITIS_SCHEMA.DIM_SIGNALS_XD
    WHERE LATITUDE IS NOT NULL 
    AND LONGITUDE IS NOT NULL
    """
    
    try:
        return _session.sql(query).to_pandas()
    except Exception as e:
        st.error(f"Error fetching signals data: {e}")
        return pd.DataFrame()


@st.cache_data
def get_travel_time_data(_session, start_date, end_date, signal_ids=None, approach=None, valid_geometry=None):
    """
    Get travel time analytics data with filters.
    """
    if _session is None:
        return pd.DataFrame()
    
    # Normalize dates to ISO strings
    try:
        start_date_str = pd.to_datetime(start_date).strftime('%Y-%m-%d')
        end_date_str = pd.to_datetime(end_date).strftime('%Y-%m-%d')
    except Exception:
        start_date_str = str(start_date)
        end_date_str = str(end_date)

    # Interpolate start/end dates into the query
    query = f"""
    SELECT 
        tta.XD,
        tta.TIMESTAMP,
        tta.TRAVEL_TIME_SECONDS,
        tta.PREDICTION,
        tta.ANOMALY,
        tta.ORIGINATED_ANOMALY,
        ds.ID,
        ds.LATITUDE,
        ds.LONGITUDE,
        ds.APPROACH,
        ds.VALID_GEOMETRY
    FROM TRAVEL_TIME_ANALYTICS tta
    JOIN TPAU_DB.TPAU_RITIS_SCHEMA.DIM_SIGNALS_XD ds ON tta.XD = ds.XD
    WHERE tta.TIMESTAMP >= '{start_date_str}'
    AND tta.TIMESTAMP <= '{end_date_str}'
    """
    
    if signal_ids:
        # Ensure all IDs are strings for SQL IN clause
        ids_str = "', '".join(map(str, signal_ids))
        query += f" AND ds.ID IN ('{ids_str}')"
    
    if approach is not None:
        query += f" AND ds.APPROACH = {approach}"
        
    if valid_geometry is not None:
        query += f" AND ds.VALID_GEOMETRY = {valid_geometry}"
    
    query += " ORDER BY tta.TIMESTAMP"
    
    try:
        return _session.sql(query).to_pandas()
    except Exception as e:
        st.error(f"Error fetching travel time data: {e}")
        return pd.DataFrame()


@st.cache_data
def get_anomaly_summary(_session, start_date, end_date, signal_ids=None, approach=None, valid_geometry=None, anomaly_type="All"):
    """
    Get anomaly summary data for map visualization.
    """
    if _session is None:
        return pd.DataFrame()
    
    # Normalize dates to ISO strings
    try:
        start_date_str = pd.to_datetime(start_date).strftime('%Y-%m-%d')
        end_date_str = pd.to_datetime(end_date).strftime('%Y-%m-%d')
    except Exception:
        start_date_str = str(start_date)
        end_date_str = str(end_date)
    
    # Base query for anomaly counts
    anomaly_filter = ""
    if anomaly_type == "Point Source":
        anomaly_filter = " AND tta.ORIGINATED_ANOMALY = TRUE"
    elif anomaly_type == "All":
        anomaly_filter = " AND tta.ANOMALY = TRUE"
    
    query = f"""
    SELECT 
        ds.ID,
        ds.LATITUDE,
        ds.LONGITUDE,
        ds.APPROACH,
        ds.VALID_GEOMETRY,
        COUNT(CASE WHEN tta.ANOMALY = TRUE THEN 1 END) as ANOMALY_COUNT,
        COUNT(CASE WHEN tta.ORIGINATED_ANOMALY = TRUE THEN 1 END) as POINT_SOURCE_COUNT
    FROM TRAVEL_TIME_ANALYTICS tta
    JOIN TPAU_DB.TPAU_RITIS_SCHEMA.DIM_SIGNALS_XD ds ON tta.XD = ds.XD
    WHERE tta.TIMESTAMP >= '{start_date_str}'
    AND tta.TIMESTAMP <= '{end_date_str}'
    {anomaly_filter}
    """
    
    if signal_ids:
        ids_str = "', '".join(map(str, signal_ids))
        query += f" AND ds.ID IN ('{ids_str}')"
    
    if approach is not None:
        query += f" AND ds.APPROACH = {approach}"
        
    if valid_geometry is not None:
        query += f" AND ds.VALID_GEOMETRY = {valid_geometry}"
    
    query += " GROUP BY ds.ID, ds.LATITUDE, ds.LONGITUDE, ds.APPROACH, ds.VALID_GEOMETRY"
    
    try:
        return _session.sql(query).to_pandas()
    except Exception as e:
        st.error(f"Error fetching anomaly data: {e}")
        return pd.DataFrame()


@st.cache_data
def get_travel_time_aggregated(_session, start_date, end_date, signal_ids=None, approach=None, valid_geometry=None):
    """
    Get aggregated travel time data by timestamp (sum of all travel times grouped by timestamp).
    """
    if _session is None:
        return pd.DataFrame()
    
    # Normalize dates to ISO strings
    try:
        start_date_str = pd.to_datetime(start_date).strftime('%Y-%m-%d')
        end_date_str = pd.to_datetime(end_date).strftime('%Y-%m-%d')
    except Exception:
        start_date_str = str(start_date)
        end_date_str = str(end_date)

    # Query to aggregate travel times by timestamp
    query = f"""
    SELECT 
        tta.TIMESTAMP,
        SUM(tta.TRAVEL_TIME_SECONDS) as TOTAL_TRAVEL_TIME_SECONDS
    FROM TRAVEL_TIME_ANALYTICS tta
    JOIN TPAU_DB.TPAU_RITIS_SCHEMA.DIM_SIGNALS_XD ds ON tta.XD = ds.XD
    WHERE tta.TIMESTAMP >= '{start_date_str}'
    AND tta.TIMESTAMP <= '{end_date_str}'
    """
    
    if signal_ids:
        # Ensure all IDs are strings for SQL IN clause
        ids_str = "', '".join(map(str, signal_ids))
        query += f" AND ds.ID IN ('{ids_str}')"
    
    if approach is not None:
        query += f" AND ds.APPROACH = {approach}"
        
    if valid_geometry is not None:
        query += f" AND ds.VALID_GEOMETRY = {valid_geometry}"
    
    query += " GROUP BY tta.TIMESTAMP ORDER BY tta.TIMESTAMP"
    
    try:
        return _session.sql(query).to_pandas()
    except Exception as e:
        st.error(f"Error fetching aggregated travel time data: {e}")
        return pd.DataFrame()


@st.cache_data
def get_anomaly_aggregated(_session, start_date, end_date, signal_ids=None, approach=None, valid_geometry=None):
    """
    Get aggregated anomaly data by timestamp (sum of predictions and actual travel times grouped by timestamp).
    """
    if _session is None:
        return pd.DataFrame()
    
    # Normalize dates to ISO strings
    try:
        start_date_str = pd.to_datetime(start_date).strftime('%Y-%m-%d')
        end_date_str = pd.to_datetime(end_date).strftime('%Y-%m-%d')
    except Exception:
        start_date_str = str(start_date)
        end_date_str = str(end_date)

    # Query to aggregate predictions and actual values by timestamp
    query = f"""
    SELECT 
        tta.TIMESTAMP,
        SUM(tta.TRAVEL_TIME_SECONDS) as TOTAL_ACTUAL_TRAVEL_TIME,
        SUM(tta.PREDICTION) as TOTAL_PREDICTION
    FROM TRAVEL_TIME_ANALYTICS tta
    JOIN TPAU_DB.TPAU_RITIS_SCHEMA.DIM_SIGNALS_XD ds ON tta.XD = ds.XD
    WHERE tta.TIMESTAMP >= '{start_date_str}'
    AND tta.TIMESTAMP <= '{end_date_str}'
    AND tta.PREDICTION IS NOT NULL
    """
    
    if signal_ids:
        # Ensure all IDs are strings for SQL IN clause
        ids_str = "', '".join(map(str, signal_ids))
        query += f" AND ds.ID IN ('{ids_str}')"
    
    if approach is not None:
        query += f" AND ds.APPROACH = {approach}"
        
    if valid_geometry is not None:
        query += f" AND ds.VALID_GEOMETRY = {valid_geometry}"
    
    query += " GROUP BY tta.TIMESTAMP ORDER BY tta.TIMESTAMP"
    
    try:
        return _session.sql(query).to_pandas()
    except Exception as e:
        st.error(f"Error fetching aggregated anomaly data: {e}")
        return pd.DataFrame()


@st.cache_data
def get_travel_time_summary(_session, start_date, end_date, signal_ids=None, approach=None, valid_geometry=None):
    """
    Get travel time summary for map visualization.
    """
    if _session is None:
        return pd.DataFrame()
    
    # Normalize dates to ISO strings
    try:
        start_date_str = pd.to_datetime(start_date).strftime('%Y-%m-%d')
        end_date_str = pd.to_datetime(end_date).strftime('%Y-%m-%d')
    except Exception:
        start_date_str = str(start_date)
        end_date_str = str(end_date)
    
    query = f"""
    SELECT 
        ds.ID,
        ds.LATITUDE,
        ds.LONGITUDE,
        ds.APPROACH,
        ds.VALID_GEOMETRY,
        SUM(tta.TRAVEL_TIME_SECONDS) as TOTAL_TRAVEL_TIME,
        AVG(tta.TRAVEL_TIME_SECONDS) as AVG_TRAVEL_TIME,
        COUNT(*) as RECORD_COUNT
    FROM TRAVEL_TIME_ANALYTICS tta
    JOIN TPAU_DB.TPAU_RITIS_SCHEMA.DIM_SIGNALS_XD ds ON tta.XD = ds.XD
    WHERE tta.TIMESTAMP >= '{start_date_str}'
    AND tta.TIMESTAMP <= '{end_date_str}'
    """
    
    if signal_ids:
        ids_str = "', '".join(map(str, signal_ids))
        query += f" AND ds.ID IN ('{ids_str}')"
    
    if approach is not None:
        query += f" AND ds.APPROACH = {approach}"
        
    if valid_geometry is not None:
        query += f" AND ds.VALID_GEOMETRY = {valid_geometry}"
    
    query += " GROUP BY ds.ID, ds.LATITUDE, ds.LONGITUDE, ds.APPROACH, ds.VALID_GEOMETRY"
    
    try:
        return _session.sql(query).to_pandas()
    except Exception as e:
        st.error(f"Error fetching travel time summary: {e}")
        return pd.DataFrame()
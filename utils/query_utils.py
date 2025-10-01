"""
Query utilities for building common SQL patterns and handling Snowflake results
"""

import pandas as pd
from typing import List, Optional, Dict, Any
from datetime import datetime


def normalize_date(date_str: str) -> str:
    """
    Normalize date string to YYYY-MM-DD format.
    Handles various input formats gracefully.

    Args:
        date_str: Date string in various formats

    Returns:
        Normalized date string in YYYY-MM-DD format
    """
    try:
        return pd.to_datetime(date_str).strftime('%Y-%m-%d')
    except Exception:
        return str(date_str)


def build_xd_dimension_query(
    signal_ids: Optional[List[str]] = None,
    approach: Optional[str] = None,
    valid_geometry: Optional[str] = None,
    include_xd_only: bool = False
) -> str:
    """
    Build dimension table query with common filters.
    Reusable pattern extracted from all endpoints.

    Args:
        signal_ids: List of signal IDs to filter
        approach: 'true'/'false' string for approach filter
        valid_geometry: 'valid'/'invalid'/'all' for geometry filter
        include_xd_only: If True, only SELECT XD (for XD lookups)

    Returns:
        SQL query string
    """
    if include_xd_only:
        select_clause = "SELECT XD"
    else:
        select_clause = """SELECT
            ID,
            LATITUDE,
            LONGITUDE,
            APPROACH,
            VALID_GEOMETRY,
            XD"""

    query = f"""
    {select_clause}
    FROM DIM_SIGNALS_XD
    WHERE LATITUDE IS NOT NULL
    AND LONGITUDE IS NOT NULL
    """

    if signal_ids:
        ids_str = "', '".join(map(str, signal_ids))
        query += f" AND ID IN ('{ids_str}')"

    if approach is not None and approach != '':
        approach_bool = 'TRUE' if approach.lower() == 'true' else 'FALSE'
        query += f" AND APPROACH = {approach_bool}"

    if valid_geometry is not None and valid_geometry != '' and valid_geometry != 'all':
        if valid_geometry == 'valid':
            query += " AND VALID_GEOMETRY = TRUE"
        elif valid_geometry == 'invalid':
            query += " AND VALID_GEOMETRY = FALSE"

    return query


def extract_xd_values(dim_result) -> List[int]:
    """
    Extract XD values from dimension query result.
    Handles Snowflake Row objects efficiently.

    Args:
        dim_result: Snowflake query result (list of Row objects)

    Returns:
        List of XD integer values
    """
    xd_values = []
    for row in dim_result:
        row_dict = row.as_dict()
        xd = row_dict.get('XD')
        if xd is not None:
            xd_values.append(xd)
    return xd_values


def build_xd_filter(xd_values: List[int]) -> str:
    """
    Build SQL IN clause for XD filtering.

    Args:
        xd_values: List of XD integers

    Returns:
        SQL fragment like "AND XD IN (123, 456, 789)"
    """
    if not xd_values:
        return ""

    xd_str = ', '.join(map(str, xd_values))
    return f" AND XD IN ({xd_str})"


def create_xd_lookup_dict(dim_result) -> Dict[int, Dict[str, Any]]:
    """
    Create XD -> signal info mapping from dimension query result.
    Used for joining analytics data with dimension data.

    Args:
        dim_result: Snowflake query result (list of Row objects)

    Returns:
        Dictionary mapping XD to signal info dict
    """
    xd_dict = {}
    for row in dim_result:
        row_dict = row.as_dict()
        xd = row_dict.get('XD')
        if xd is not None:
            xd_dict[xd] = row_dict
    return xd_dict


def get_aggregation_table(start_date: str, end_date: str) -> str:
    """
    Determine which table/view to query based on date range.

    Args:
        start_date: Start date string (YYYY-MM-DD format)
        end_date: End date string (YYYY-MM-DD format)

    Returns:
        Table name: TRAVEL_TIME_ANALYTICS, TRAVEL_TIME_HOURLY_AGG, or TRAVEL_TIME_DAILY_AGG
    """
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        days = (end - start).days

        if days < 4:
            return "TRAVEL_TIME_ANALYTICS"
        elif days <= 7:
            return "TRAVEL_TIME_HOURLY_AGG"
        else:
            return "TRAVEL_TIME_DAILY_AGG"
    except Exception:
        # Default to base table if date parsing fails
        return "TRAVEL_TIME_ANALYTICS"


def build_time_of_day_filter(start_hour: Optional[int] = None, end_hour: Optional[int] = None) -> str:
    """
    Build SQL filter clause for time-of-day filtering.

    Args:
        start_hour: Start hour (0-23), None means no filter
        end_hour: End hour (0-23), None means no filter

    Returns:
        SQL fragment like "AND HOUR_OF_DAY BETWEEN 15 AND 18" or empty string
    """
    if start_hour is None or end_hour is None:
        return ""

    try:
        start = int(start_hour)
        end = int(end_hour)

        # Validate hour range
        if not (0 <= start <= 23 and 0 <= end <= 23):
            return ""

        # If filtering all day (0-23), no need for filter
        if start == 0 and end == 23:
            return ""

        return f" AND HOUR_OF_DAY BETWEEN {start} AND {end}"
    except (ValueError, TypeError):
        return ""

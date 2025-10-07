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


def get_aggregation_level(start_date: str, end_date: str) -> str:
    """
    Determine aggregation level based on date range.

    Args:
        start_date: Start date string (YYYY-MM-DD format)
        end_date: End date string (YYYY-MM-DD format)

    Returns:
        Aggregation level: "none" (15-min), "hourly", or "daily"
    """
    try:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        days = (end - start).days

        if days < 4:
            return "none"
        elif days <= 7:
            return "hourly"
        else:
            return "daily"
    except Exception:
        # Default to no aggregation if date parsing fails
        return "none"


def get_aggregation_table(start_date: str, end_date: str) -> str:
    """
    DEPRECATED: Kept for backward compatibility with anomalies routes.
    Use get_aggregation_level() for new code.

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


def build_day_of_week_filter(day_of_week: Optional[List[int]] = None) -> str:
    """
    Build SQL filter clause for day-of-week filtering with DIM_DATE join.

    Args:
        day_of_week: List of day numbers (1=Mon, 2=Tue, ..., 7=Sun), None means no filter

    Returns:
        SQL fragment like "INNER JOIN DIM_DATE d ON t.DATE_ONLY = d.DATE_ONLY AND d.DAY_OF_WEEK_ISO IN (1, 2, 3)" or empty string
    """
    if day_of_week is None or len(day_of_week) == 0:
        return ""

    try:
        # Validate day numbers
        days = [int(d) for d in day_of_week if 1 <= int(d) <= 7]
        if not days:
            return ""

        days_str = ', '.join(map(str, days))
        # Qualify DATE_ONLY with table aliases to avoid ambiguity
        return f" INNER JOIN DIM_DATE d ON t.DATE_ONLY = d.DATE_ONLY AND d.DAY_OF_WEEK_ISO IN ({days_str})"
    except (ValueError, TypeError):
        return ""


def build_time_of_day_filter(start_hour: Optional[int] = None, end_hour: Optional[int] = None) -> str:
    """
    Build SQL filter clause for time-of-day filtering.

    Args:
        start_hour: Start hour (0-23), None means no filter
        end_hour: End hour (0-23), None means no filter

    Returns:
        SQL fragment like "AND TIME_15MIN BETWEEN '15:00:00' AND '18:59:59'" or empty string
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

        # Format as TIME values
        start_time = f"{start:02d}:00:00"
        end_time = f"{end:02d}:59:59"
        return f" AND TIME_15MIN BETWEEN '{start_time}' AND '{end_time}'"
    except (ValueError, TypeError):
        return ""


def build_legend_join(
    legend_by: Optional[str] = None,
    max_entities: int = 10
) -> tuple[str, str]:
    """
    Build SQL JOIN clause for legend grouping.
    Uses SELECT DISTINCT to handle many-to-many relationship in DIM_SIGNALS_XD.

    IMPORTANT: This returns a simple JOIN that should be added AFTER the main WHERE clause.
    The subquery to limit entities should use the SAME filters as the main query.

    Args:
        legend_by: Field to group by ('xd', 'bearing', 'county', 'roadname', 'id', or None)
        max_entities: Maximum number of legend entities to return

    Returns:
        Tuple of (join_clause, legend_field_name)
        - join_clause: SQL JOIN fragment (just "INNER JOIN DIM_SIGNALS_XD s ON t.XD = s.XD")
        - legend_field_name: Column name for legend field or empty string
    """
    if not legend_by or legend_by == 'none':
        return ("", "")

    # Map legend_by parameter to actual column name
    legend_field_map = {
        'xd': 'XD',
        'bearing': 'BEARING',
        'county': 'COUNTY',
        'roadname': 'ROADNAME',
        'id': 'ID'
    }

    legend_field = legend_field_map.get(legend_by.lower())
    if not legend_field:
        return ("", "")

    # Return simple join - the WHERE clause will be built by the endpoint
    join_clause = "INNER JOIN DIM_SIGNALS_XD s ON t.XD = s.XD"

    return (join_clause, legend_field)


def build_legend_filter(
    legend_field: str,
    max_entities: int,
    xd_filter: str = "",
    start_date: str = "",
    end_date: str = "",
    time_filter: str = "",
    dow_join: str = ""
) -> str:
    """
    Build WHERE clause to limit legend entities.

    SIMPLIFIED LOGIC: Just query DIM_SIGNALS_XD with the same XD filter as main query.
    No need to join TRAVEL_TIME_ANALYTICS or apply date/time filters in subquery since
    the main query already filters by XD, and we just want distinct legend values from those XDs.

    SPECIAL CASE FOR XD: When legend_field is 'XD', we need to query TRAVEL_TIME_ANALYTICS
    to get the top XDs by data volume, not just the dimension table.

    Args:
        legend_field: The field to limit (e.g., 'COUNTY', 'BEARING', 'XD')
        max_entities: Maximum number of entities
        xd_filter: XD filter like "AND XD IN (...)" - ONLY this is needed

    Returns:
        SQL fragment like "AND s.COUNTY IN (SELECT DISTINCT ...)"
    """
    if not legend_field:
        return ""

    # Special handling for XD legend - query actual data table for top XDs by volume
    if legend_field == 'XD':
        where_clause = ""
        if xd_filter:
            clean_xd = xd_filter.strip()
            if clean_xd.startswith('AND '):
                clean_xd = clean_xd[4:].strip()
            where_clause = f"WHERE {clean_xd}"

        # Query TRAVEL_TIME_ANALYTICS for top XDs by data volume within date range
        if start_date and end_date:
            date_filter = f"DATE_ONLY BETWEEN '{start_date}' AND '{end_date}'"
            if where_clause:
                where_clause += f" AND {date_filter}"
            else:
                where_clause = f"WHERE {date_filter}"

        subquery = f"""SELECT XD
            FROM TRAVEL_TIME_ANALYTICS
            {where_clause}
            GROUP BY XD
            ORDER BY COUNT(*) DESC
            LIMIT {max_entities}"""

        return f" AND t.XD IN ({subquery})"

    # For non-XD legend fields, query DIM_SIGNALS_XD
    where_clause = ""
    if xd_filter:
        # Remove leading AND and strip, then replace table alias
        clean_xd = xd_filter.strip()
        if clean_xd.startswith('AND '):
            clean_xd = clean_xd[4:].strip()
        # Replace t.XD with sub_s.XD
        clean_xd = clean_xd.replace('t.XD', 'sub_s.XD')
        if clean_xd and 'sub_s.XD' not in clean_xd and 'XD IN' in clean_xd:
            # Handle case where it's just "XD IN (...)"
            clean_xd = clean_xd.replace('XD IN', 'sub_s.XD IN')
        if clean_xd:
            where_clause = f"WHERE {clean_xd}"

    # Build simple subquery - just query DIM_SIGNALS_XD
    subquery = f"""SELECT DISTINCT sub_s.{legend_field}
        FROM DIM_SIGNALS_XD sub_s
        {where_clause}
        LIMIT {max_entities}"""

    return f" AND s.{legend_field} IN ({subquery})"

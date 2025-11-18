"""
Anomalies API Routes - Returns Arrow data directly
Optimized for low-latency small queries
"""

import pyarrow as pa
from flask import Blueprint, request, jsonify

from config import MAX_ANOMALY_LEGEND_ENTITIES
from database import get_snowflake_session, is_auth_error
from services.report_service import fetch_monitoring_anomaly_rows
from utils.error_handler import handle_auth_error_retry
from utils.arrow_utils import (
    serialize_arrow_to_ipc,
    create_empty_arrow_response,
    create_arrow_response,
    snowflake_result_to_arrow
)
from utils.query_utils import (
    normalize_date,
    build_xd_dimension_query,
    extract_xd_values,
    build_xd_filter,
    build_xd_filter_with_joins,
    build_filter_joins_and_where,
    create_xd_lookup_dict,
    get_aggregation_table,
    build_time_of_day_filter,
    build_day_of_week_filter,
    get_aggregation_level,
    build_legend_join,
    build_legend_filter
)

anomalies_bp = Blueprint('anomalies', __name__)


@anomalies_bp.route('/anomaly-summary')
def get_anomaly_summary():
    """Get anomaly summary data for map visualization as Arrow (metrics only)

    OPTIMIZATION: Returns only ID and metrics (no dimension data like NAME, LATITUDE, LONGITUDE)
    Dimension data should be cached on client from /dim-signals endpoint
    """
    # Get query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    signal_ids = request.args.getlist('signal_ids')
    maintained_by = request.args.get('maintained_by', 'all')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    anomaly_type = request.args.get('anomaly_type', default='All')
    start_hour = request.args.get('start_hour')
    start_minute = request.args.get('start_minute')
    end_hour = request.args.get('end_hour')
    end_minute = request.args.get('end_minute')
    day_of_week = request.args.getlist('day_of_week')

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, start_minute, end_hour, end_minute)

    # Build day-of-week filter
    dow_filter = build_day_of_week_filter(day_of_week)

    def execute_query():
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise Exception("Unable to establish database connection")

        # Build filter joins for efficient SQL filtering
        filter_join, filter_where = build_filter_joins_and_where(
            signal_ids, maintained_by, approach, valid_geometry
        )

        # Build WHERE clause parts
        where_parts = [f"t.DATE_ONLY BETWEEN '{start_date_str}' AND '{end_date_str}'"]

        if filter_where:
            where_parts.append(filter_where)

        if time_filter:
            clean_time = time_filter.strip()
            if clean_time.startswith('AND '):
                clean_time = clean_time[4:]
            clean_time = clean_time.replace('TIME_15MIN', 't.TIME_15MIN')
            where_parts.append(clean_time)

        where_clause = " AND ".join(where_parts)

        # Build FROM clause
        from_clause = f"""FROM TRAVEL_TIME_ANALYTICS t
        {dow_filter}
        INNER JOIN DIM_SIGNALS_XD xd ON t.XD = xd.XD
        INNER JOIN DIM_SIGNALS s ON xd.ID = s.ID"""

        # Single query that does all filtering in SQL - SIGNAL-LEVEL aggregation
        # Groups by signal only (not XD) to return one row per signal
        # OPTIMIZATION: Returns only ID and metrics (no dimension data like NAME, LATITUDE, LONGITUDE)
        # Dimension data should be cached on client from /dim-signals endpoint
        analytics_query = f"""
        SELECT
            s.ID,
            SUM(CASE WHEN t.ANOMALY = TRUE THEN 1 ELSE 0 END) AS ANOMALY_COUNT,
            SUM(CASE WHEN t.ORIGINATED_ANOMALY = TRUE THEN 1 ELSE 0 END) AS POINT_SOURCE_COUNT,
            COUNT(*) AS RECORD_COUNT
        {from_clause}
        WHERE {where_clause}
        GROUP BY s.ID
        ORDER BY s.ID
        """

        arrow_data = session.sql(analytics_query).to_arrow()
        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        return create_arrow_response(arrow_bytes)

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /anomaly-summary: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching anomaly data: {e}", 500


@anomalies_bp.route('/anomaly-summary-xd')
def get_anomaly_summary_xd():
    """Get XD segment-level anomaly metrics as Arrow (metrics only)

    OPTIMIZATION: Returns only XD and metrics (no dimension data like BEARING, ROADNAME, etc.)
    Dimension data should be cached on client from /dim-signals-xd endpoint
    """
    # Get query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    signal_ids = request.args.getlist('signal_ids')
    maintained_by = request.args.get('maintained_by', 'all')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    anomaly_type = request.args.get('anomaly_type', default='All')
    start_hour = request.args.get('start_hour')
    start_minute = request.args.get('start_minute')
    end_hour = request.args.get('end_hour')
    end_minute = request.args.get('end_minute')
    day_of_week = request.args.getlist('day_of_week')

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, start_minute, end_hour, end_minute)

    # Build day-of-week filter
    dow_filter = build_day_of_week_filter(day_of_week)

    def execute_query():
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise Exception("Unable to establish database connection")

        # Build filter joins for efficient SQL filtering
        filter_join, filter_where = build_filter_joins_and_where(
            signal_ids, maintained_by, approach, valid_geometry
        )

        # Build WHERE clause parts
        where_parts = [f"t.DATE_ONLY BETWEEN '{start_date_str}' AND '{end_date_str}'"]

        if filter_where:
            where_parts.append(filter_where)

        if time_filter:
            clean_time = time_filter.strip()
            if clean_time.startswith('AND '):
                clean_time = clean_time[4:]
            clean_time = clean_time.replace('TIME_15MIN', 't.TIME_15MIN')
            where_parts.append(clean_time)

        where_clause = " AND ".join(where_parts)

        # Build FROM clause
        from_clause = f"""FROM TRAVEL_TIME_ANALYTICS t
        {dow_filter}
        INNER JOIN DIM_SIGNALS_XD xd ON t.XD = xd.XD
        INNER JOIN DIM_SIGNALS s ON xd.ID = s.ID"""

        # Single query that does all filtering in SQL - XD-LEVEL aggregation
        # Groups by XD to return one row per XD segment
        # OPTIMIZATION: Returns only XD and metrics (no dimension data like BEARING, ROADNAME, etc.)
        # Dimension data should be cached on client from /dim-signals-xd endpoint
        analytics_query = f"""
        SELECT
            xd.XD,
            SUM(CASE WHEN t.ANOMALY = TRUE THEN 1 ELSE 0 END) AS ANOMALY_COUNT,
            SUM(CASE WHEN t.ORIGINATED_ANOMALY = TRUE THEN 1 ELSE 0 END) AS POINT_SOURCE_COUNT,
            COUNT(*) AS RECORD_COUNT
        {from_clause}
        WHERE {where_clause}
        GROUP BY xd.XD
        ORDER BY xd.XD
        """

        arrow_data = session.sql(analytics_query).to_arrow()
        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        return create_arrow_response(arrow_bytes)

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /anomaly-summary-xd: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching XD anomaly summary: {e}", 500


@anomalies_bp.route('/anomaly-aggregated')
def get_anomaly_aggregated():
    """Get aggregated anomaly data by timestamp as Arrow (with dynamic aggregation)"""
    # Get query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    signal_ids = request.args.getlist('signal_ids')
    xd_segments = request.args.getlist('xd_segments')
    maintained_by = request.args.get('maintained_by', 'all')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    start_hour = request.args.get('start_hour')
    start_minute = request.args.get('start_minute')
    end_hour = request.args.get('end_hour')
    end_minute = request.args.get('end_minute')
    day_of_week = request.args.getlist('day_of_week')
    legend_by = request.args.get('legend_by')  # New parameter

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    # Determine aggregation level based on date range (matching TTI pattern)
    agg_level = get_aggregation_level(start_date_str, end_date_str)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, start_minute, end_hour, end_minute)

    # Build day-of-week filter
    dow_filter = build_day_of_week_filter(day_of_week)

    def execute_query():
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise Exception("Unable to establish database connection")

        # Determine filtering strategy
        if xd_segments:
            # Map interaction - use direct XD list (small, efficient)
            xd_values = [int(xd) for xd in xd_segments]
            xd_filter = build_xd_filter(xd_values)
            filter_join = ""
            filter_where = ""
        elif signal_ids or maintained_by != 'all' or approach or (valid_geometry and valid_geometry != 'all'):
            # Filter panel - use efficient join-based filtering (ALL filtering in SQL)
            filter_join, filter_where = build_filter_joins_and_where(
                signal_ids, maintained_by, approach, valid_geometry
            )
            xd_filter = ""  # No XD list needed - filtering via joins
        else:
            # NO filters - query all
            xd_filter = ""
            filter_join = ""
            filter_where = ""

        # Build legend join if legend_by is specified
        legend_join, legend_field = build_legend_join(legend_by, MAX_ANOMALY_LEGEND_ENTITIES)

        # Build query based on aggregation level
        if agg_level == "none":
            # No aggregation: query by TIMESTAMP (15-minute intervals)
            timestamp_expr = "t.TIMESTAMP"
        elif agg_level == "hourly":
            # Hourly aggregation: truncate timestamp to hour
            timestamp_expr = "DATE_TRUNC('HOUR', t.TIMESTAMP) as TIMESTAMP"
        else:  # daily
            # Daily aggregation: use DATE_ONLY, cast to TIMESTAMP_NTZ
            timestamp_expr = "CAST(t.DATE_ONLY AS TIMESTAMP_NTZ) as TIMESTAMP"

        # Determine SELECT and GROUP BY clauses based on legend
        if legend_field:
            select_clause = f"{timestamp_expr}, legend_xd.{legend_field} AS LEGEND_GROUP, SUM(t.TRAVEL_TIME_SECONDS) as TOTAL_ACTUAL_TRAVEL_TIME, SUM(t.PREDICTION) as TOTAL_PREDICTION"
            group_by_clause = "GROUP BY 1, 2\nORDER BY 1, 2"
        else:
            select_clause = f"{timestamp_expr}, SUM(t.TRAVEL_TIME_SECONDS) as TOTAL_ACTUAL_TRAVEL_TIME, SUM(t.PREDICTION) as TOTAL_PREDICTION"
            group_by_clause = "GROUP BY 1\nORDER BY 1"

        # Build WHERE clause parts
        where_parts = [f"t.DATE_ONLY BETWEEN '{start_date_str}' AND '{end_date_str}'"]
        where_parts.append("t.PREDICTION IS NOT NULL")

        # Add XD filter if present (for map interactions with xd_segments)
        if xd_filter:
            clean_xd = xd_filter.strip()
            if clean_xd.startswith('AND '):
                clean_xd = clean_xd[4:]
            clean_xd = clean_xd.replace('XD', 't.XD')
            where_parts.append(clean_xd)

        # Add filter WHERE conditions (for maintainedBy, approach, validGeometry)
        if filter_where:
            where_parts.append(filter_where)

        # Add time filter if present
        if time_filter:
            clean_time = time_filter.strip()
            if clean_time.startswith('AND '):
                clean_time = clean_time[4:]
            clean_time = clean_time.replace('TIME_15MIN', 't.TIME_15MIN')
            where_parts.append(clean_time)

        where_clause = " AND ".join(where_parts)

        # Build FROM clause
        from_clause = f"""FROM TRAVEL_TIME_ANALYTICS t
        {dow_filter}"""

        # Add filter joins (for maintainedBy, approach, validGeometry)
        if filter_join:
            from_clause += f"\n{filter_join}"

        # Add legend join if specified
        if legend_join:
            from_clause += f"\n{legend_join}"

            # Add legend filter to limit number of entities
            legend_entity_filter = build_legend_filter(
                legend_field=legend_field,
                max_entities=MAX_ANOMALY_LEGEND_ENTITIES,
                xd_filter=xd_filter,
                start_date=start_date_str,
                end_date=end_date_str,
                time_filter=time_filter,
                dow_join=dow_filter
            )
            where_clause += legend_entity_filter

        # Construct final query
        query = f"""
        SELECT
            {select_clause}
        {from_clause}
        WHERE {where_clause}
        {group_by_clause}
        """

        arrow_data = session.sql(query).to_arrow()
        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        return create_arrow_response(arrow_bytes)

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /anomaly-aggregated: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching aggregated anomaly data: {e}", 500


@anomalies_bp.route('/anomaly-by-time-of-day')
def get_anomaly_by_time_of_day():
    """Get aggregated anomaly data by time of day (15-min intervals) as Arrow"""
    # Get query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    signal_ids = request.args.getlist('signal_ids')
    xd_segments = request.args.getlist('xd_segments')
    maintained_by = request.args.get('maintained_by', 'all')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    day_of_week = request.args.getlist('day_of_week')
    start_hour = request.args.get('start_hour')
    start_minute = request.args.get('start_minute')
    end_hour = request.args.get('end_hour')
    end_minute = request.args.get('end_minute')
    legend_by = request.args.get('legend_by')  # New parameter

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    # Build day-of-week filter
    dow_filter = build_day_of_week_filter(day_of_week)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, start_minute, end_hour, end_minute)

    def execute_query():
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise Exception("Unable to establish database connection")

        # Determine filtering strategy
        if xd_segments:
            # Map interaction - use direct XD list (small, efficient)
            xd_values = [int(xd) for xd in xd_segments]
            xd_filter = build_xd_filter(xd_values)
            filter_join = ""
            filter_where = ""
        elif signal_ids or maintained_by != 'all' or approach or (valid_geometry and valid_geometry != 'all'):
            # Filter panel - use efficient join-based filtering (ALL filtering in SQL)
            filter_join, filter_where = build_filter_joins_and_where(
                signal_ids, maintained_by, approach, valid_geometry
            )
            xd_filter = ""  # No XD list needed - filtering via joins
        else:
            # NO filters - query all
            xd_filter = ""
            filter_join = ""
            filter_where = ""

        # Build legend join if legend_by is specified
        legend_join, legend_field = build_legend_join(legend_by, MAX_ANOMALY_LEGEND_ENTITIES)

        # Determine SELECT and GROUP BY clauses based on legend
        if legend_field:
            select_clause = f"t.TIME_15MIN AS TIME_OF_DAY, legend_xd.{legend_field} AS LEGEND_GROUP, SUM(t.TRAVEL_TIME_SECONDS) as TOTAL_ACTUAL_TRAVEL_TIME, SUM(t.PREDICTION) as TOTAL_PREDICTION"
            group_by_clause = "GROUP BY 1, 2\nORDER BY 1, 2"
        else:
            select_clause = f"t.TIME_15MIN AS TIME_OF_DAY, SUM(t.TRAVEL_TIME_SECONDS) as TOTAL_ACTUAL_TRAVEL_TIME, SUM(t.PREDICTION) as TOTAL_PREDICTION"
            group_by_clause = "GROUP BY 1\nORDER BY 1"

        # Build WHERE clause parts
        where_parts = [f"t.DATE_ONLY BETWEEN '{start_date_str}' AND '{end_date_str}'"]
        where_parts.append("t.PREDICTION IS NOT NULL")

        # Add XD filter if present (for map interactions with xd_segments)
        if xd_filter:
            clean_xd = xd_filter.strip()
            if clean_xd.startswith('AND '):
                clean_xd = clean_xd[4:]
            clean_xd = clean_xd.replace('XD', 't.XD')
            where_parts.append(clean_xd)

        # Add filter WHERE conditions (for maintainedBy, approach, validGeometry)
        if filter_where:
            where_parts.append(filter_where)

        # Add time filter if present
        if time_filter:
            clean_time = time_filter.strip()
            if clean_time.startswith('AND '):
                clean_time = clean_time[4:]
            clean_time = clean_time.replace('TIME_15MIN', 't.TIME_15MIN')
            where_parts.append(clean_time)

        where_clause = " AND ".join(where_parts)

        # Build FROM clause
        from_clause = f"""FROM TRAVEL_TIME_ANALYTICS t
        {dow_filter}"""

        # Add filter joins (for maintainedBy, approach, validGeometry)
        if filter_join:
            from_clause += f"\n{filter_join}"

        # Add legend join if specified
        if legend_join:
            from_clause += f"\n{legend_join}"

            # Add legend filter to limit number of entities
            legend_entity_filter = build_legend_filter(
                legend_field=legend_field,
                max_entities=MAX_ANOMALY_LEGEND_ENTITIES,
                xd_filter=xd_filter,
                start_date=start_date_str,
                end_date=end_date_str,
                time_filter=time_filter,
                dow_join=dow_filter
            )
            where_clause += legend_entity_filter

        # Construct final query
        query = f"""
        SELECT
            {select_clause}
        {from_clause}
        WHERE {where_clause}
        {group_by_clause}
        """

        arrow_data = session.sql(query).to_arrow()
        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        return create_arrow_response(arrow_bytes)

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /anomaly-by-time-of-day: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching time-of-day anomaly data: {e}", 500


@anomalies_bp.route('/anomaly-percent-aggregated')
def get_anomaly_percent_aggregated():
    """Get aggregated anomaly percentage data by timestamp as Arrow (with dynamic aggregation)"""
    # Get query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    signal_ids = request.args.getlist('signal_ids')
    xd_segments = request.args.getlist('xd_segments')
    maintained_by = request.args.get('maintained_by', 'all')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    start_hour = request.args.get('start_hour')
    start_minute = request.args.get('start_minute')
    end_hour = request.args.get('end_hour')
    end_minute = request.args.get('end_minute')
    day_of_week = request.args.getlist('day_of_week')
    legend_by = request.args.get('legend_by')  # New parameter

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    # Determine aggregation level based on date range
    agg_level = get_aggregation_level(start_date_str, end_date_str)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, start_minute, end_hour, end_minute)

    # Build day-of-week filter
    dow_filter = build_day_of_week_filter(day_of_week)

    def execute_query():
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise Exception("Unable to establish database connection")

        # Determine filtering strategy
        if xd_segments:
            # Map interaction - use direct XD list (small, efficient)
            xd_values = [int(xd) for xd in xd_segments]
            xd_filter = build_xd_filter(xd_values)
            filter_join = ""
            filter_where = ""
        elif signal_ids or maintained_by != 'all' or approach or (valid_geometry and valid_geometry != 'all'):
            # Filter panel - use efficient join-based filtering (ALL filtering in SQL)
            filter_join, filter_where = build_filter_joins_and_where(
                signal_ids, maintained_by, approach, valid_geometry
            )
            xd_filter = ""  # No XD list needed - filtering via joins
        else:
            # NO filters - query all
            xd_filter = ""
            filter_join = ""
            filter_where = ""

        # Build legend join if legend_by is specified
        legend_join, legend_field = build_legend_join(legend_by, MAX_ANOMALY_LEGEND_ENTITIES)

        # Build query based on aggregation level
        if agg_level == "none":
            # No aggregation: query by TIMESTAMP (15-minute intervals)
            timestamp_expr = "t.TIMESTAMP"
        elif agg_level == "hourly":
            # Hourly aggregation: truncate timestamp to hour
            timestamp_expr = "DATE_TRUNC('HOUR', t.TIMESTAMP) as TIMESTAMP"
        else:  # daily
            # Daily aggregation: use DATE_ONLY, cast to TIMESTAMP_NTZ
            timestamp_expr = "CAST(t.DATE_ONLY AS TIMESTAMP_NTZ) as TIMESTAMP"

        # Determine SELECT and GROUP BY clauses based on legend
        # Calculate anomaly percentage: (anomaly count / total records) * 100
        if legend_field:
            select_clause = f"{timestamp_expr}, legend_xd.{legend_field} AS LEGEND_GROUP, (SUM(CASE WHEN t.ANOMALY = TRUE THEN 1 ELSE 0 END)::FLOAT / COUNT(*)) * 100 as ANOMALY_PERCENT"
            group_by_clause = "GROUP BY 1, 2\nORDER BY 1, 2"
        else:
            select_clause = f"{timestamp_expr}, (SUM(CASE WHEN t.ANOMALY = TRUE THEN 1 ELSE 0 END)::FLOAT / COUNT(*)) * 100 as ANOMALY_PERCENT"
            group_by_clause = "GROUP BY 1\nORDER BY 1"

        # Build WHERE clause parts
        where_parts = [f"t.DATE_ONLY BETWEEN '{start_date_str}' AND '{end_date_str}'"]

        # Add XD filter if present (for map interactions with xd_segments)
        if xd_filter:
            clean_xd = xd_filter.strip()
            if clean_xd.startswith('AND '):
                clean_xd = clean_xd[4:]
            clean_xd = clean_xd.replace('XD', 't.XD')
            where_parts.append(clean_xd)

        # Add filter WHERE conditions (for maintainedBy, approach, validGeometry)
        if filter_where:
            where_parts.append(filter_where)

        # Add time filter if present
        if time_filter:
            clean_time = time_filter.strip()
            if clean_time.startswith('AND '):
                clean_time = clean_time[4:]
            clean_time = clean_time.replace('TIME_15MIN', 't.TIME_15MIN')
            where_parts.append(clean_time)

        where_clause = " AND ".join(where_parts)

        # Build FROM clause
        from_clause = f"""FROM TRAVEL_TIME_ANALYTICS t
        {dow_filter}"""

        # Add filter joins (for maintainedBy, approach, validGeometry)
        if filter_join:
            from_clause += f"\n{filter_join}"

        # Add legend join if specified
        if legend_join:
            from_clause += f"\n{legend_join}"

            # Add legend filter to limit number of entities
            legend_entity_filter = build_legend_filter(
                legend_field=legend_field,
                max_entities=MAX_ANOMALY_LEGEND_ENTITIES,
                xd_filter=xd_filter,
                start_date=start_date_str,
                end_date=end_date_str,
                time_filter=time_filter,
                dow_join=dow_filter
            )
            where_clause += legend_entity_filter

        # Construct final query
        query = f"""
        SELECT
            {select_clause}
        {from_clause}
        WHERE {where_clause}
        {group_by_clause}
        """

        arrow_data = session.sql(query).to_arrow()
        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        return create_arrow_response(arrow_bytes)

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /anomaly-percent-aggregated: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching anomaly percent aggregated data: {e}", 500


@anomalies_bp.route('/anomaly-percent-by-time-of-day')
def get_anomaly_percent_by_time_of_day():
    """Get aggregated anomaly percentage data by time of day (15-min intervals) as Arrow"""
    # Get query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    signal_ids = request.args.getlist('signal_ids')
    xd_segments = request.args.getlist('xd_segments')
    maintained_by = request.args.get('maintained_by', 'all')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    day_of_week = request.args.getlist('day_of_week')
    start_hour = request.args.get('start_hour')
    start_minute = request.args.get('start_minute')
    end_hour = request.args.get('end_hour')
    end_minute = request.args.get('end_minute')
    legend_by = request.args.get('legend_by')  # New parameter

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    # Build day-of-week filter
    dow_filter = build_day_of_week_filter(day_of_week)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, start_minute, end_hour, end_minute)

    def execute_query():
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise Exception("Unable to establish database connection")

        # Determine filtering strategy
        if xd_segments:
            # Map interaction - use direct XD list (small, efficient)
            xd_values = [int(xd) for xd in xd_segments]
            xd_filter = build_xd_filter(xd_values)
            filter_join = ""
            filter_where = ""
        elif signal_ids or maintained_by != 'all' or approach or (valid_geometry and valid_geometry != 'all'):
            # Filter panel - use efficient join-based filtering (ALL filtering in SQL)
            filter_join, filter_where = build_filter_joins_and_where(
                signal_ids, maintained_by, approach, valid_geometry
            )
            xd_filter = ""  # No XD list needed - filtering via joins
        else:
            # NO filters - query all
            xd_filter = ""
            filter_join = ""
            filter_where = ""

        # Build legend join if legend_by is specified
        legend_join, legend_field = build_legend_join(legend_by, MAX_ANOMALY_LEGEND_ENTITIES)

        # Determine SELECT and GROUP BY clauses based on legend
        # Calculate anomaly percentage: (anomaly count / total records) * 100
        if legend_field:
            select_clause = f"t.TIME_15MIN AS TIME_OF_DAY, legend_xd.{legend_field} AS LEGEND_GROUP, (SUM(CASE WHEN t.ANOMALY = TRUE THEN 1 ELSE 0 END)::FLOAT / COUNT(*)) * 100 as ANOMALY_PERCENT"
            group_by_clause = "GROUP BY 1, 2\nORDER BY 1, 2"
        else:
            select_clause = f"t.TIME_15MIN AS TIME_OF_DAY, (SUM(CASE WHEN t.ANOMALY = TRUE THEN 1 ELSE 0 END)::FLOAT / COUNT(*)) * 100 as ANOMALY_PERCENT"
            group_by_clause = "GROUP BY 1\nORDER BY 1"

        # Build WHERE clause parts
        where_parts = [f"t.DATE_ONLY BETWEEN '{start_date_str}' AND '{end_date_str}'"]

        # Add XD filter if present (for map interactions with xd_segments)
        if xd_filter:
            clean_xd = xd_filter.strip()
            if clean_xd.startswith('AND '):
                clean_xd = clean_xd[4:]
            clean_xd = clean_xd.replace('XD', 't.XD')
            where_parts.append(clean_xd)

        # Add filter WHERE conditions (for maintainedBy, approach, validGeometry)
        if filter_where:
            where_parts.append(filter_where)

        # Add time filter if present
        if time_filter:
            clean_time = time_filter.strip()
            if clean_time.startswith('AND '):
                clean_time = clean_time[4:]
            clean_time = clean_time.replace('TIME_15MIN', 't.TIME_15MIN')
            where_parts.append(clean_time)

        where_clause = " AND ".join(where_parts)

        # Build FROM clause
        from_clause = f"""FROM TRAVEL_TIME_ANALYTICS t
        {dow_filter}"""

        # Add filter joins (for maintainedBy, approach, validGeometry)
        if filter_join:
            from_clause += f"\n{filter_join}"

        # Add legend join if specified
        if legend_join:
            from_clause += f"\n{legend_join}"

            # Add legend filter to limit number of entities
            legend_entity_filter = build_legend_filter(
                legend_field=legend_field,
                max_entities=MAX_ANOMALY_LEGEND_ENTITIES,
                xd_filter=xd_filter,
                start_date=start_date_str,
                end_date=end_date_str,
                time_filter=time_filter,
                dow_join=dow_filter
            )
            where_clause += legend_entity_filter

        # Construct final query
        query = f"""
        SELECT
            {select_clause}
        {from_clause}
        WHERE {where_clause}
        {group_by_clause}
        """

        arrow_data = session.sql(query).to_arrow()
        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        return create_arrow_response(arrow_bytes)

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /anomaly-percent-by-time-of-day: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching time-of-day anomaly percent data: {e}", 500


@anomalies_bp.route('/monitoring-anomalies')
def get_monitoring_anomalies():
    """Return anomaly segments for the monitoring report as JSON."""
    from datetime import datetime, date  # Local import to avoid circular issues in some environments

    filters = {
        "start_date": request.args.get("start_date"),
        "end_date": request.args.get("end_date"),
        "signal_ids": request.args.getlist("signal_ids"),
        "selected_signals": request.args.getlist("selected_signals"),
        "selected_xds": request.args.getlist("selected_xds"),
        "selected_signal_groups": request.args.getlist("selected_signal_groups"),
        "maintained_by": request.args.get("maintained_by"),
        "approach": request.args.get("approach"),
        "valid_geometry": request.args.get("valid_geometry"),
        "anomaly_monitoring_threshold": request.args.get("anomaly_monitoring_threshold")
        or request.args.get("monitoring_score_threshold"),
    }

    def execute_query():
        rows, threshold = fetch_monitoring_anomaly_rows(filters)
        payload = []
        target_date_value = None
        for row in rows:
            target_date = row.get("target_date")
            if isinstance(target_date, (datetime, date)):
                target_iso = target_date.isoformat()
            else:
                target_iso = str(target_date) if target_date else None
            if target_iso and not target_date_value:
                target_date_value = target_iso

            payload.append(
                {
                    "xd": row.get("xd"),
                    "roadname": row.get("roadname"),
                    "bearing": row.get("bearing"),
                    "associated_signals": row.get("associated_signals"),
                    "target_date": target_iso,
                    "time_of_day_series": [
                        {
                            "minutes": point.get("minutes"),
                            "actual": point.get("actual"),
                            "prediction": point.get("prediction"),
                        }
                        for point in row.get("time_of_day_series") or []
                    ],
                }
            )

        response = {
            "anomalies": payload,
            "target_date": target_date_value,
            "threshold": threshold,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        }
        return jsonify(response)

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as exc:
        print(f"[ERROR] /monitoring-anomalies: {exc}")
        if is_auth_error(exc):
            return "Database reconnecting - please wait", 503
        return f"Error fetching monitoring anomalies: {exc}", 500


@anomalies_bp.route('/travel-time-data')
def get_travel_time_data():
    """Get detailed travel time data for anomaly analysis as Arrow"""
    # Get query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    xd_segments = request.args.getlist('xd_segments')
    signal_ids = request.args.getlist('signal_ids')
    maintained_by = request.args.get('maintained_by', 'all')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    def execute_query():
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise Exception("Unable to establish database connection")
        # Resolve XD segments
        if xd_segments:
            # Map interaction - use direct XD list
            xd_values = [int(xd) for xd in xd_segments]
        elif signal_ids or maintained_by != 'all':
            # Filter panel - use join-based filtering
            xd_values = build_xd_filter_with_joins(
                session, signal_ids, maintained_by, approach, valid_geometry
            )
            if not xd_values:
                arrow_bytes = create_empty_arrow_response('travel_time_detail')
                return create_arrow_response(arrow_bytes)
        else:
            xd_values = None

        # Step 1: Query DIM_SIGNALS_XD to get signal info for the XD values
        dim_query = build_xd_dimension_query(signal_ids, approach, valid_geometry)

        # Add XD filter if we have specific XDs
        if xd_values:
            xd_str = ', '.join(map(str, xd_values))
            dim_query += f" AND XD IN ({xd_str})"

        dim_result = session.sql(dim_query).collect()

        if not dim_result:
            arrow_bytes = create_empty_arrow_response('travel_time_detail')
            return create_arrow_response(arrow_bytes)

        # Extract XD values and create mapping
        xd_to_signal = create_xd_lookup_dict(dim_result)
        xd_values = list(xd_to_signal.keys())

        if not xd_values:
            arrow_bytes = create_empty_arrow_response('travel_time_detail')
            return create_arrow_response(arrow_bytes)

        # Step 2: Query TRAVEL_TIME_ANALYTICS using XD values
        xd_filter = build_xd_filter(xd_values)
        query = f"""
        SELECT
            XD,
            TIMESTAMP,
            TRAVEL_TIME_SECONDS,
            PREDICTION,
            ANOMALY,
            ORIGINATED_ANOMALY
        FROM TRAVEL_TIME_ANALYTICS
        WHERE TIMESTAMP >= '{start_date_str}'
        AND TIMESTAMP <= '{end_date_str}'
        {xd_filter}
        ORDER BY TIMESTAMP
        """

        analytics_result = session.sql(query).collect()

        # Step 3: Combine results - join analytics with signal info
        xds = []
        timestamps = []
        travel_times = []
        predictions = []
        anomalies = []
        originated_anomalies = []
        ids = []
        latitudes = []
        longitudes = []
        approaches = []
        valid_geometries = []

        for row in analytics_result:
            analytics_dict = row.as_dict()
            xd = analytics_dict['XD']
            signal_info = xd_to_signal.get(xd, {})

            xds.append(xd)
            timestamps.append(analytics_dict['TIMESTAMP'])
            travel_times.append(analytics_dict['TRAVEL_TIME_SECONDS'])
            predictions.append(analytics_dict.get('PREDICTION'))
            anomalies.append(analytics_dict.get('ANOMALY'))
            originated_anomalies.append(analytics_dict.get('ORIGINATED_ANOMALY'))
            ids.append(signal_info.get('ID'))
            latitudes.append(signal_info.get('LATITUDE'))
            longitudes.append(signal_info.get('LONGITUDE'))
            approaches.append(signal_info.get('APPROACH'))
            valid_geometries.append(signal_info.get('VALID_GEOMETRY'))

        result_table = pa.table({
            'XD': xds,
            'TIMESTAMP': timestamps,
            'TRAVEL_TIME_SECONDS': travel_times,
            'PREDICTION': predictions,
            'ANOMALY': anomalies,
            'ORIGINATED_ANOMALY': originated_anomalies,
            'ID': ids,
            'LATITUDE': latitudes,
            'LONGITUDE': longitudes,
            'APPROACH': approaches,
            'VALID_GEOMETRY': valid_geometries
        })

        arrow_bytes = serialize_arrow_to_ipc(result_table)
        return create_arrow_response(arrow_bytes)

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /travel-time-data: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching travel time data: {e}", 500

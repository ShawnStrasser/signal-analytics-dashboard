"""
Before/After Comparison API Routes - Returns Arrow data for before/after analysis
Compares travel time metrics between two time periods
"""

import time
from flask import Blueprint, request

from config import DEBUG_BACKEND_TIMING, MAX_LEGEND_ENTITIES
from database import get_snowflake_session, is_auth_error
from utils.arrow_utils import create_arrow_response, snowflake_result_to_arrow
from utils.error_handler import handle_auth_error_retry
from utils.query_utils import (
    normalize_date,
    build_filter_joins_and_where,
    build_time_of_day_filter,
    build_day_of_week_filter,
    build_legend_join,
    build_xd_filter
)

before_after_bp = Blueprint('before_after', __name__)


@before_after_bp.route('/before-after-summary')
def get_before_after_summary():
    """Get before/after travel time summary for map visualization (signal-level) as Arrow"""
    request_start = time.time()

    # Get query parameters
    before_start = request.args.get('before_start_date')
    before_end = request.args.get('before_end_date')
    after_start = request.args.get('after_start_date')
    after_end = request.args.get('after_end_date')
    signal_ids = request.args.getlist('signal_ids')
    maintained_by = request.args.get('maintained_by', 'all')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    start_hour = request.args.get('start_hour')
    start_minute = request.args.get('start_minute')
    end_hour = request.args.get('end_hour')
    end_minute = request.args.get('end_minute')
    day_of_week = request.args.getlist('day_of_week')
    remove_anomalies = request.args.get('remove_anomalies', 'false').lower() == 'true'

    # Normalize dates
    before_start_str = normalize_date(before_start)
    before_end_str = normalize_date(before_end)
    after_start_str = normalize_date(after_start)
    after_end_str = normalize_date(after_end)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, start_minute, end_hour, end_minute)

    # Build day-of-week filter
    dow_filter = build_day_of_week_filter(day_of_week)

    if DEBUG_BACKEND_TIMING:
        print(f"\n[TIMING] /before-after-summary START")
        print(f"  Params: before={before_start_str} to {before_end_str}, after={after_start_str} to {after_end_str}")

    def execute_query():
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise Exception("Unable to establish database connection")

        # Build filter joins for efficient SQL filtering
        filter_join, filter_where = build_filter_joins_and_where(
            signal_ids, maintained_by, approach, valid_geometry
        )

        query_start = time.time()

        # Build WHERE clause parts (shared between before and after)
        def build_where_clause(start_date, end_date):
            where_parts = [f"t.DATE_ONLY BETWEEN '{start_date}' AND '{end_date}'"]
            if filter_where:
                where_parts.append(filter_where)
            if time_filter:
                clean_time = time_filter.strip()
                if clean_time.startswith('AND '):
                    clean_time = clean_time[4:]
                clean_time = clean_time.replace('TIME_15MIN', 't.TIME_15MIN')
                where_parts.append(clean_time)
            if remove_anomalies:
                where_parts.append("t.IS_ANOMALY = FALSE")
            return " AND ".join(where_parts)

        before_where = build_where_clause(before_start_str, before_end_str)
        after_where = build_where_clause(after_start_str, after_end_str)

        # Build FROM clause
        from_clause = f"""FROM TRAVEL_TIME_ANALYTICS t
        {dow_filter}
        INNER JOIN FREEFLOW f ON t.XD = f.XD
        INNER JOIN DIM_SIGNALS_XD xd ON t.XD = xd.XD
        INNER JOIN DIM_SIGNALS s ON xd.ID = s.ID"""

        # CTE query with before and after periods joined
        query = f"""
        WITH before_data AS (
            SELECT
                s.ID,
                AVG(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) AS TTI_BEFORE
            {from_clause}
            WHERE {before_where}
            GROUP BY s.ID
        ),
        after_data AS (
            SELECT
                s.ID,
                AVG(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) AS TTI_AFTER
            {from_clause}
            WHERE {after_where}
            GROUP BY s.ID
        )
        SELECT
            COALESCE(b.ID, a.ID) AS ID,
            COALESCE(b.TTI_BEFORE, 0) AS TTI_BEFORE,
            COALESCE(a.TTI_AFTER, 0) AS TTI_AFTER,
            COALESCE(a.TTI_AFTER, 0) - COALESCE(b.TTI_BEFORE, 0) AS TTI_DIFF
        FROM before_data b
        FULL OUTER JOIN after_data a ON b.ID = a.ID
        ORDER BY ID
        """

        if DEBUG_BACKEND_TIMING:
            print(f"  [QUERY]:\n{query}\n")

        arrow_data = session.sql(query).to_arrow()
        query_time = (time.time() - query_start) * 1000

        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        total_time = (time.time() - request_start) * 1000

        if DEBUG_BACKEND_TIMING:
            print(f"  [1] Before/After query: {query_time:.2f}ms ({arrow_data.num_rows} rows)")
            print(f"  [TOTAL] /before-after-summary: {total_time:.2f}ms\n")

        return create_arrow_response(arrow_bytes)

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /before-after-summary: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching before/after summary: {e}", 500


@before_after_bp.route('/before-after-summary-xd')
def get_before_after_summary_xd():
    """Get before/after travel time summary for map visualization (XD segment-level) as Arrow"""
    request_start = time.time()

    # Get query parameters (same as signal-level)
    before_start = request.args.get('before_start_date')
    before_end = request.args.get('before_end_date')
    after_start = request.args.get('after_start_date')
    after_end = request.args.get('after_end_date')
    signal_ids = request.args.getlist('signal_ids')
    maintained_by = request.args.get('maintained_by', 'all')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    start_hour = request.args.get('start_hour')
    start_minute = request.args.get('start_minute')
    end_hour = request.args.get('end_hour')
    end_minute = request.args.get('end_minute')
    day_of_week = request.args.getlist('day_of_week')
    remove_anomalies = request.args.get('remove_anomalies', 'false').lower() == 'true'

    # Normalize dates
    before_start_str = normalize_date(before_start)
    before_end_str = normalize_date(before_end)
    after_start_str = normalize_date(after_start)
    after_end_str = normalize_date(after_end)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, start_minute, end_hour, end_minute)

    # Build day-of-week filter
    dow_filter = build_day_of_week_filter(day_of_week)

    if DEBUG_BACKEND_TIMING:
        print(f"\n[TIMING] /before-after-summary-xd START")

    def execute_query():
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise Exception("Unable to establish database connection")

        # Build filter joins for efficient SQL filtering
        filter_join, filter_where = build_filter_joins_and_where(
            signal_ids, maintained_by, approach, valid_geometry
        )

        query_start = time.time()

        # Build WHERE clause parts (shared between before and after)
        def build_where_clause(start_date, end_date):
            where_parts = [f"t.DATE_ONLY BETWEEN '{start_date}' AND '{end_date}'"]
            if filter_where:
                where_parts.append(filter_where)
            if time_filter:
                clean_time = time_filter.strip()
                if clean_time.startswith('AND '):
                    clean_time = clean_time[4:]
                clean_time = clean_time.replace('TIME_15MIN', 't.TIME_15MIN')
                where_parts.append(clean_time)
            if remove_anomalies:
                where_parts.append("t.IS_ANOMALY = FALSE")
            return " AND ".join(where_parts)

        before_where = build_where_clause(before_start_str, before_end_str)
        after_where = build_where_clause(after_start_str, after_end_str)

        # Build FROM clause
        from_clause = f"""FROM TRAVEL_TIME_ANALYTICS t
        {dow_filter}
        INNER JOIN FREEFLOW f ON t.XD = f.XD
        INNER JOIN DIM_SIGNALS_XD xd ON t.XD = xd.XD
        INNER JOIN DIM_SIGNALS s ON xd.ID = s.ID"""

        # CTE query with before and after periods joined (XD-level aggregation)
        query = f"""
        WITH before_data AS (
            SELECT
                xd.XD,
                AVG(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) AS TTI_BEFORE
            {from_clause}
            WHERE {before_where}
            GROUP BY xd.XD
        ),
        after_data AS (
            SELECT
                xd.XD,
                AVG(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) AS TTI_AFTER
            {from_clause}
            WHERE {after_where}
            GROUP BY xd.XD
        )
        SELECT
            COALESCE(b.XD, a.XD) AS XD,
            COALESCE(b.TTI_BEFORE, 0) AS TTI_BEFORE,
            COALESCE(a.TTI_AFTER, 0) AS TTI_AFTER,
            COALESCE(a.TTI_AFTER, 0) - COALESCE(b.TTI_BEFORE, 0) AS TTI_DIFF
        FROM before_data b
        FULL OUTER JOIN after_data a ON b.XD = a.XD
        ORDER BY XD
        """

        arrow_data = session.sql(query).to_arrow()
        query_time = (time.time() - query_start) * 1000

        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        total_time = (time.time() - request_start) * 1000

        if DEBUG_BACKEND_TIMING:
            print(f"  [1] Before/After XD query: {query_time:.2f}ms ({arrow_data.num_rows} rows)")
            print(f"  [TOTAL] /before-after-summary-xd: {total_time:.2f}ms\n")

        return create_arrow_response(arrow_bytes)

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /before-after-summary-xd: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching before/after XD summary: {e}", 500


@before_after_bp.route('/before-after-aggregated')
def get_before_after_aggregated():
    """Get before/after travel time data aggregated by timestamp (DATE/TIME mode) as Arrow"""
    request_start = time.time()

    # Get query parameters
    before_start = request.args.get('before_start_date')
    before_end = request.args.get('before_end_date')
    after_start = request.args.get('after_start_date')
    after_end = request.args.get('after_end_date')
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
    legend_by = request.args.get('legend_by')
    remove_anomalies = request.args.get('remove_anomalies', 'false').lower() == 'true'

    # Normalize dates
    before_start_str = normalize_date(before_start)
    before_end_str = normalize_date(before_end)
    after_start_str = normalize_date(after_start)
    after_end_str = normalize_date(after_end)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, start_minute, end_hour, end_minute)

    # Build day-of-week filter
    dow_filter = build_day_of_week_filter(day_of_week)

    if DEBUG_BACKEND_TIMING:
        print(f"\n[TIMING] /before-after-aggregated START")
        print(f"  legend_by={legend_by}")

    def execute_query():
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise Exception("Unable to establish database connection")

        # Determine filtering strategy
        if xd_segments:
            # Map interaction - use direct XD list
            xd_values = [int(xd) for xd in xd_segments]
            xd_filter = build_xd_filter(xd_values)
            filter_join = ""
            filter_where = ""
        elif signal_ids or maintained_by != 'all' or approach or (valid_geometry and valid_geometry != 'all'):
            # Filter panel - use join-based filtering
            filter_join, filter_where = build_filter_joins_and_where(
                signal_ids, maintained_by, approach, valid_geometry
            )
            xd_filter = ""
        else:
            # NO filters - query all
            xd_filter = ""
            filter_join = ""
            filter_where = ""

        # Build legend join if legend_by is specified
        legend_join, legend_field = build_legend_join(legend_by, MAX_LEGEND_ENTITIES)

        query_start = time.time()

        # Build WHERE clause parts (shared between before and after)
        def build_where_clause(start_date, end_date):
            where_parts = [f"t.DATE_ONLY BETWEEN '{start_date}' AND '{end_date}'"]
            if xd_filter:
                clean_xd = xd_filter.strip()
                if clean_xd.startswith('AND '):
                    clean_xd = clean_xd[4:]
                clean_xd = clean_xd.replace('XD', 't.XD')
                where_parts.append(clean_xd)
            if filter_where:
                where_parts.append(filter_where)
            if time_filter:
                clean_time = time_filter.strip()
                if clean_time.startswith('AND '):
                    clean_time = clean_time[4:]
                clean_time = clean_time.replace('TIME_15MIN', 't.TIME_15MIN')
                where_parts.append(clean_time)
            if remove_anomalies:
                where_parts.append("t.IS_ANOMALY = FALSE")
            return " AND ".join(where_parts)

        before_where = build_where_clause(before_start_str, before_end_str)
        after_where = build_where_clause(after_start_str, after_end_str)

        # Build FROM clause (no aggregation - keep timestamps)
        from_clause_base = f"""FROM TRAVEL_TIME_ANALYTICS t
        {dow_filter}
        INNER JOIN FREEFLOW f ON t.XD = f.XD"""

        if filter_join:
            from_clause_base += f"\n{filter_join}"

        if legend_join:
            from_clause_base += f"\n{legend_join}"

        # Determine SELECT clause based on legend
        if legend_field:
            select_clause = f"t.TIMESTAMP, legend_xd.{legend_field} AS LEGEND_GROUP, AVG(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) as TRAVEL_TIME_INDEX, 'Before' AS PERIOD"
            group_by = f"GROUP BY t.TIMESTAMP, legend_xd.{legend_field}"
        else:
            select_clause = "t.TIMESTAMP, AVG(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) as TRAVEL_TIME_INDEX, 'Before' AS PERIOD"
            group_by = "GROUP BY t.TIMESTAMP"

        # UNION query for before and after periods
        query = f"""
        SELECT {select_clause}
        {from_clause_base}
        WHERE {before_where}
        {group_by}

        UNION ALL

        SELECT {select_clause.replace("'Before'", "'After'")}
        {from_clause_base}
        WHERE {after_where}
        {group_by}

        ORDER BY TIMESTAMP, PERIOD
        """

        if DEBUG_BACKEND_TIMING:
            print(f"  [QUERY]:\n{query}\n")

        arrow_data = session.sql(query).to_arrow()
        query_time = (time.time() - query_start) * 1000

        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        total_time = (time.time() - request_start) * 1000

        if DEBUG_BACKEND_TIMING:
            print(f"  [1] Before/After aggregated query: {query_time:.2f}ms ({arrow_data.num_rows} rows)")
            print(f"  [TOTAL] /before-after-aggregated: {total_time:.2f}ms\n")

        return create_arrow_response(arrow_bytes)

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /before-after-aggregated: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching before/after aggregated data: {e}", 500


@before_after_bp.route('/before-after-by-time-of-day')
def get_before_after_by_time_of_day():
    """Get before/after travel time data aggregated by time of day (TIME OF DAY mode) as Arrow"""
    request_start = time.time()

    # Get query parameters
    before_start = request.args.get('before_start_date')
    before_end = request.args.get('before_end_date')
    after_start = request.args.get('after_start_date')
    after_end = request.args.get('after_end_date')
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
    legend_by = request.args.get('legend_by')
    remove_anomalies = request.args.get('remove_anomalies', 'false').lower() == 'true'

    # Normalize dates
    before_start_str = normalize_date(before_start)
    before_end_str = normalize_date(before_end)
    after_start_str = normalize_date(after_start)
    after_end_str = normalize_date(after_end)

    # Build day-of-week filter
    dow_filter = build_day_of_week_filter(day_of_week)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, start_minute, end_hour, end_minute)

    if DEBUG_BACKEND_TIMING:
        print(f"\n[TIMING] /before-after-by-time-of-day START")

    def execute_query():
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise Exception("Unable to establish database connection")

        # Determine filtering strategy
        if xd_segments:
            xd_values = [int(xd) for xd in xd_segments]
            xd_filter = build_xd_filter(xd_values)
            filter_join = ""
            filter_where = ""
        elif signal_ids or maintained_by != 'all' or approach or (valid_geometry and valid_geometry != 'all'):
            filter_join, filter_where = build_filter_joins_and_where(
                signal_ids, maintained_by, approach, valid_geometry
            )
            xd_filter = ""
        else:
            xd_filter = ""
            filter_join = ""
            filter_where = ""

        # Build legend join if legend_by is specified
        legend_join, legend_field = build_legend_join(legend_by, MAX_LEGEND_ENTITIES)

        query_start = time.time()

        # Build WHERE clause parts (shared between before and after)
        def build_where_clause(start_date, end_date):
            where_parts = [f"t.DATE_ONLY BETWEEN '{start_date}' AND '{end_date}'"]
            if xd_filter:
                clean_xd = xd_filter.strip()
                if clean_xd.startswith('AND '):
                    clean_xd = clean_xd[4:]
                clean_xd = clean_xd.replace('XD', 't.XD')
                where_parts.append(clean_xd)
            if filter_where:
                where_parts.append(filter_where)
            if time_filter:
                clean_time = time_filter.strip()
                if clean_time.startswith('AND '):
                    clean_time = clean_time[4:]
                clean_time = clean_time.replace('TIME_15MIN', 't.TIME_15MIN')
                where_parts.append(clean_time)
            if remove_anomalies:
                where_parts.append("t.IS_ANOMALY = FALSE")
            return " AND ".join(where_parts)

        before_where = build_where_clause(before_start_str, before_end_str)
        after_where = build_where_clause(after_start_str, after_end_str)

        # Build FROM clause
        from_clause_base = f"""FROM TRAVEL_TIME_ANALYTICS t
        {dow_filter}
        INNER JOIN FREEFLOW f ON t.XD = f.XD"""

        if filter_join:
            from_clause_base += f"\n{filter_join}"

        if legend_join:
            from_clause_base += f"\n{legend_join}"

        # Determine SELECT clause based on legend
        if legend_field:
            select_clause = f"t.TIME_15MIN AS TIME_OF_DAY, legend_xd.{legend_field} AS LEGEND_GROUP, AVG(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) as TRAVEL_TIME_INDEX, 'Before' AS PERIOD"
            group_by = f"GROUP BY t.TIME_15MIN, legend_xd.{legend_field}"
        else:
            select_clause = "t.TIME_15MIN AS TIME_OF_DAY, AVG(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) as TRAVEL_TIME_INDEX, 'Before' AS PERIOD"
            group_by = "GROUP BY t.TIME_15MIN"

        # UNION query for before and after periods
        query = f"""
        SELECT {select_clause}
        {from_clause_base}
        WHERE {before_where}
        {group_by}

        UNION ALL

        SELECT {select_clause.replace("'Before'", "'After'")}
        {from_clause_base}
        WHERE {after_where}
        {group_by}

        ORDER BY TIME_OF_DAY, PERIOD
        """

        arrow_data = session.sql(query).to_arrow()
        query_time = (time.time() - query_start) * 1000

        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        total_time = (time.time() - request_start) * 1000

        if DEBUG_BACKEND_TIMING:
            print(f"  [1] Before/After by time of day query: {query_time:.2f}ms ({arrow_data.num_rows} rows)")
            print(f"  [TOTAL] /before-after-by-time-of-day: {total_time:.2f}ms\n")

        return create_arrow_response(arrow_bytes)

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /before-after-by-time-of-day: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching before/after time of day data: {e}", 500

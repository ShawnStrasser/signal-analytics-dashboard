"""
Changepoints API Routes

Provides aggregated metrics, tabular listings, and detail data for the changepoints
page. Responses use Apache Arrow streams for consistency with the rest of the API.
"""

import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, request

from config import DEBUG_BACKEND_TIMING, TIMEZONE
from database import get_snowflake_session, is_auth_error
from utils.arrow_utils import (
    create_arrow_response,
    snowflake_result_to_arrow
)
from utils.error_handler import handle_auth_error_retry
from utils.query_utils import normalize_date, build_filter_joins_and_where

changepoints_bp = Blueprint('changepoints', __name__)


def _parse_positive_float(value, default=0.0):
    """Parse a float value and return its absolute value (non-negative)."""
    try:
        numeric = float(value)
        if numeric < 0:
            numeric = abs(numeric)
        return numeric
    except (TypeError, ValueError):
        return default


def _sanitize_string_list(values):
    """Escape single quotes in string list for SQL IN clauses."""
    sanitized = []
    for val in values or []:
        if val is None:
            continue
        sanitized.append(str(val).replace("'", "''"))
    return sanitized


def _sanitize_int_list(values):
    """Convert values to integers (as strings) for SQL IN clauses."""
    ints = []
    for val in values or []:
        try:
            ints.append(str(int(val)))
        except (TypeError, ValueError):
            continue
    return ints


def _local_zone() -> Optional[ZoneInfo]:
    try:
        return ZoneInfo(TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _to_local_naive(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp
    zone = _local_zone()
    if zone is not None:
        return timestamp.astimezone(zone).replace(tzinfo=None)
    return timestamp.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _normalize_change_timestamp(value: str) -> str:
    """
    Convert a raw timestamp parameter to a local-time string Snowflake can compare directly.
    Accepts ISO strings (with optional timezone/Z) or epoch seconds.
    """
    text = (value or "").strip()
    if not text:
        raise ValueError("empty timestamp parameter")

    parsed: Optional[datetime] = None

    if text.isdigit():
        try:
            epoch_value = int(text)
            if len(text) > 11:  # likely milliseconds
                epoch_value = epoch_value / 1000.0
            parsed = datetime.fromtimestamp(epoch_value, tz=ZoneInfo("UTC"))
        except (ValueError, OSError):
            parsed = None
    if parsed is None:
        candidate = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            parsed = None

    if parsed is not None:
        local_naive = _to_local_naive(parsed)
        return local_naive.strftime("%Y-%m-%d %H:%M:%S")

    sanitized = text.replace("T", " ").replace("'", "''")
    if sanitized.endswith("Z"):
        sanitized = sanitized[:-1]
    return sanitized


def _build_percent_change_condition(improvement, degradation):
    """
    Build SQL condition for percent-change thresholds (decimal values).

    Returns a string like:
      "(t.PCT_CHANGE <= -0.01 OR t.PCT_CHANGE >= 0.01)"
    Falls back to "1=1" (no filtering) if both thresholds are zero.
    """
    conditions = []

    if improvement > 0:
        conditions.append(f"t.PCT_CHANGE <= {-improvement}")
    if degradation > 0:
        conditions.append(f"t.PCT_CHANGE >= {degradation}")

    if not conditions:
        return "1=1"

    joined = " OR ".join(conditions)
    return f"({joined})"


def _assemble_where_clause(
    start_date,
    end_date,
    filter_where,
    improvement,
    degradation,
    selected_signals=None,
    selected_xds=None
):
    """Compose WHERE clause for changepoint queries."""
    where_parts = [
        f"DATE(t.TIMESTAMP) BETWEEN '{start_date}' AND '{end_date}'",
        _build_percent_change_condition(improvement, degradation)
    ]

    if filter_where:
        where_parts.append(filter_where)

    sanitized_signals = _sanitize_string_list(selected_signals)
    if sanitized_signals:
        ids_str = "', '".join(sanitized_signals)
        where_parts.append(f"t.XD IN (SELECT DISTINCT XD FROM DIM_SIGNALS_XD WHERE ID IN ('{ids_str}'))")

    sanitized_xds = _sanitize_int_list(selected_xds)
    if sanitized_xds:
        xds_str = ", ".join(sanitized_xds)
        where_parts.append(f"t.XD IN ({xds_str})")

    return " AND ".join(where_parts)


def _build_filtered_dim_components(
    signal_ids,
    maintained_by,
    approach,
    valid_geometry
):
    """Return JOIN and WHERE fragments for DIM_SIGNALS_XD filtering without unnecessary joins."""
    sanitized_ids = _sanitize_string_list(signal_ids)
    join_clause = ""
    where_parts = []

    if sanitized_ids:
        ids_str = "', '".join(sanitized_ids)
        where_parts.append(f"dim.ID IN ('{ids_str}')")

    if approach is not None and approach != '':
        approach_bool = 'TRUE' if str(approach).lower() == 'true' else 'FALSE'
        where_parts.append(f"dim.APPROACH = {approach_bool}")

    if valid_geometry is not None and valid_geometry != '' and valid_geometry != 'all':
        valid = str(valid_geometry).lower()
        if valid == 'valid':
            where_parts.append("dim.VALID_GEOMETRY = TRUE")
        elif valid == 'invalid':
            where_parts.append("dim.VALID_GEOMETRY = FALSE")

    maintained = str(maintained_by or 'all').lower()
    if maintained in {'odot', 'others'}:
        join_clause = "\n        INNER JOIN DIM_SIGNALS s ON dim.ID = s.ID"
        if maintained == 'odot':
            where_parts.append("s.ODOT_MAINTAINED = TRUE")
        else:
            where_parts.append("s.ODOT_MAINTAINED = FALSE")

    where_clause = ""
    if where_parts:
        where_clause = "\n        WHERE " + " AND ".join(where_parts)

    return join_clause, where_clause


def _execute_arrow_query(query):
    """Execute a Snowflake query and return Arrow response."""
    session = get_snowflake_session(retry=True, max_retries=2)
    if not session:
        raise Exception("Unable to establish database connection")

    arrow_data = session.sql(query).to_arrow()

    arrow_bytes = snowflake_result_to_arrow(arrow_data)
    return create_arrow_response(arrow_bytes)


@changepoints_bp.route('/changepoints-map-signals')
def get_changepoints_map_signals():
    """Aggregate changepoints by signal for map visualization."""
    request_start = time.time()

    # Base filters
    start_date = normalize_date(request.args.get('start_date'))
    end_date = normalize_date(request.args.get('end_date'))
    signal_ids = request.args.getlist('signal_ids')
    maintained_by = request.args.get('maintained_by', 'all')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')

    improvement = _parse_positive_float(request.args.get('pct_change_improvement'), 0.01)
    degradation = _parse_positive_float(request.args.get('pct_change_degradation'), 0.01)

    filter_join, filter_where = build_filter_joins_and_where(
        signal_ids,
        maintained_by,
        approach,
        valid_geometry
    )

    needs_signal_join = "DIM_SIGNALS s" in filter_join
    join_signal_clause = "\n        INNER JOIN DIM_SIGNALS s ON xd.ID = s.ID" if needs_signal_join else ""

    where_clause = _assemble_where_clause(
        start_date,
        end_date,
        filter_where,
        improvement,
        degradation
    )

    query = f"""
    WITH filtered_cp AS (
        SELECT
            t.XD,
            t.TIMESTAMP,
            t.PCT_CHANGE,
            t.AVG_DIFF,
            t.SCORE,
            xd.ID AS SIGNAL_ID,
            xd.ROADNAME,
            xd.BEARING
        FROM CHANGEPOINTS t
        INNER JOIN DIM_SIGNALS_XD xd ON t.XD = xd.XD{join_signal_clause}
        WHERE {where_clause}
    ),
    signal_stats AS (
        SELECT
            SIGNAL_ID,
            SUM(ABS(PCT_CHANGE)) AS ABS_PCT_SUM,
            AVG(PCT_CHANGE) AS AVG_PCT_CHANGE,
            COUNT(*) AS CHANGEPOINT_COUNT
        FROM filtered_cp
        GROUP BY SIGNAL_ID
    ),
    top_cp AS (
        SELECT
            SIGNAL_ID,
            XD,
            TIMESTAMP,
            PCT_CHANGE,
            AVG_DIFF,
            ROADNAME,
            BEARING,
            ROW_NUMBER() OVER (
                PARTITION BY SIGNAL_ID
                ORDER BY ABS(PCT_CHANGE) DESC, TIMESTAMP DESC
            ) AS RN
        FROM filtered_cp
    )
    SELECT
        stats.SIGNAL_ID AS ID,
        stats.ABS_PCT_SUM,
        stats.AVG_PCT_CHANGE,
        stats.CHANGEPOINT_COUNT,
        top.XD AS TOP_XD,
        top.TIMESTAMP AS TOP_TIMESTAMP,
        top.PCT_CHANGE AS TOP_PCT_CHANGE,
        top.AVG_DIFF AS TOP_AVG_DIFF,
        top.ROADNAME AS TOP_ROADNAME,
        top.BEARING AS TOP_BEARING
    FROM signal_stats stats
    LEFT JOIN (SELECT * FROM top_cp WHERE RN = 1) top
        ON stats.SIGNAL_ID = top.SIGNAL_ID
    ORDER BY stats.ABS_PCT_SUM DESC, stats.SIGNAL_ID
    """

    if DEBUG_BACKEND_TIMING:
        print(f"\n[TIMING] /changepoints-map-signals START")
        print(f"  Params: {where_clause}")

    def execute_query():
        result = _execute_arrow_query(query)
        if DEBUG_BACKEND_TIMING:
            total_time = (time.time() - request_start) * 1000
            print(f"[TIMING] /changepoints-map-signals COMPLETE in {total_time:.2f}ms")
        return result

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /changepoints-map-signals: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching changepoint map signal data: {e}", 500


@changepoints_bp.route('/changepoints-map-xd')
def get_changepoints_map_xd():
    """Aggregate changepoints by XD segment for map visualization."""
    request_start = time.time()

    start_date = normalize_date(request.args.get('start_date'))
    end_date = normalize_date(request.args.get('end_date'))
    signal_ids = request.args.getlist('signal_ids')
    maintained_by = request.args.get('maintained_by', 'all')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')

    improvement = _parse_positive_float(request.args.get('pct_change_improvement'), 0.01)
    degradation = _parse_positive_float(request.args.get('pct_change_degradation'), 0.01)

    filter_join, filter_where = build_filter_joins_and_where(
        signal_ids,
        maintained_by,
        approach,
        valid_geometry
    )

    needs_signal_join = "DIM_SIGNALS s" in filter_join
    join_signal_clause = "\n        INNER JOIN DIM_SIGNALS s ON xd.ID = s.ID" if needs_signal_join else ""

    where_clause = _assemble_where_clause(
        start_date,
        end_date,
        filter_where,
        improvement,
        degradation
    )

    query = f"""
    WITH filtered_cp AS (
        SELECT
            t.XD,
            t.TIMESTAMP,
            t.PCT_CHANGE,
            t.AVG_DIFF,
            t.SCORE,
            xd.ROADNAME,
            xd.BEARING
        FROM CHANGEPOINTS t
        INNER JOIN (
            SELECT DISTINCT XD, ID, ROADNAME, BEARING, APPROACH, VALID_GEOMETRY
            FROM DIM_SIGNALS_XD
        ) xd ON t.XD = xd.XD{join_signal_clause}
        WHERE {where_clause}
    ),
    xd_stats AS (
        SELECT
            XD,
            SUM(ABS(PCT_CHANGE)) AS ABS_PCT_SUM,
            AVG(PCT_CHANGE) AS AVG_PCT_CHANGE,
            COUNT(*) AS CHANGEPOINT_COUNT
        FROM filtered_cp
        GROUP BY XD
    ),
    top_cp AS (
        SELECT
            XD,
            TIMESTAMP,
            PCT_CHANGE,
            AVG_DIFF,
            ROADNAME,
            BEARING,
            ROW_NUMBER() OVER (
                PARTITION BY XD
                ORDER BY ABS(PCT_CHANGE) DESC, TIMESTAMP DESC
            ) AS RN
        FROM filtered_cp
    )
    SELECT
        stats.XD,
        stats.ABS_PCT_SUM,
        stats.AVG_PCT_CHANGE,
        stats.CHANGEPOINT_COUNT,
        top.TIMESTAMP AS TOP_TIMESTAMP,
        top.PCT_CHANGE AS TOP_PCT_CHANGE,
        top.AVG_DIFF AS TOP_AVG_DIFF,
        top.ROADNAME AS TOP_ROADNAME,
        top.BEARING AS TOP_BEARING
    FROM xd_stats stats
    LEFT JOIN (SELECT * FROM top_cp WHERE RN = 1) top
        ON stats.XD = top.XD
    ORDER BY stats.ABS_PCT_SUM DESC, stats.XD
    """

    if DEBUG_BACKEND_TIMING:
        print(f"\n[TIMING] /changepoints-map-xd START")
        print(f"  Params: {where_clause}")

    def execute_query():
        result = _execute_arrow_query(query)
        if DEBUG_BACKEND_TIMING:
            total_time = (time.time() - request_start) * 1000
            print(f"[TIMING] /changepoints-map-xd COMPLETE in {total_time:.2f}ms")
        return result

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /changepoints-map-xd: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching changepoint map XD data: {e}", 500


@changepoints_bp.route('/changepoints-table')
def get_changepoints_table():
    """Return top changepoints (limit 100) for the table with server-side sorting."""
    request_start = time.time()

    # Base filters
    start_date = normalize_date(request.args.get('start_date'))
    end_date = normalize_date(request.args.get('end_date'))
    signal_ids = request.args.getlist('signal_ids')
    maintained_by = request.args.get('maintained_by', 'all')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')

    improvement = _parse_positive_float(request.args.get('pct_change_improvement'), 0.01)
    degradation = _parse_positive_float(request.args.get('pct_change_degradation'), 0.01)

    selected_signals = request.args.getlist('selected_signals')
    selected_xds = request.args.getlist('selected_xds')

    dimension_join, dimension_where_clause = _build_filtered_dim_components(
        signal_ids,
        maintained_by,
        approach,
        valid_geometry
    )

    where_clause = _assemble_where_clause(
        start_date,
        end_date,
        "",
        improvement,
        degradation,
        selected_signals=selected_signals,
        selected_xds=selected_xds
    )

    sort_by = request.args.get('sort_by', 'timestamp').lower()
    sort_dir = request.args.get('sort_dir', 'desc').lower()

    sort_column_map = {
        'timestamp': 't.TIMESTAMP',
        'pct_change': 't.PCT_CHANGE',
        'avg_diff': 't.AVG_DIFF',
        'score': 't.SCORE'
    }
    sort_column = sort_column_map.get(sort_by, 't.TIMESTAMP')
    sort_direction = 'ASC' if sort_dir == 'asc' else 'DESC'

    query = f"""
    SELECT
        t.XD AS XD,
        t.TIMESTAMP,
        t.PCT_CHANGE,
        t.AVG_DIFF,
        t.AVG_BEFORE,
        t.AVG_AFTER,
        t.SCORE,
        xd.ROADNAME,
        xd.BEARING,
        LISTAGG(DISTINCT xd.ID, ', ') WITHIN GROUP (ORDER BY xd.ID) AS ASSOCIATED_SIGNALS
    FROM CHANGEPOINTS t
    INNER JOIN (
        SELECT DISTINCT
            dim.XD,
            dim.ID,
            dim.ROADNAME,
            dim.BEARING
        FROM DIM_SIGNALS_XD dim{dimension_join}{dimension_where_clause}
    ) xd ON t.XD = xd.XD
    WHERE {where_clause}
    GROUP BY ALL
    ORDER BY {sort_column} {sort_direction}
    LIMIT 100
    """

    if DEBUG_BACKEND_TIMING:
        print(f"\n[TIMING] /changepoints-table START")
        print(f"  Params: {where_clause}")
        print(f"  Sort: {sort_column} {sort_direction}")

    def execute_query():
        result = _execute_arrow_query(query)
        if DEBUG_BACKEND_TIMING:
            total_time = (time.time() - request_start) * 1000
            print(f"[TIMING] /changepoints-table COMPLETE in {total_time:.2f}ms")
        return result

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /changepoints-table: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching changepoint table data: {e}", 500


@changepoints_bp.route('/changepoints-detail')
def get_changepoint_detail():
    """Return travel time data (before/after) for a specific changepoint."""
    request_start = time.time()

    xd_value = request.args.get('xd')
    change_timestamp = request.args.get('timestamp')

    if not xd_value or not change_timestamp:
        return "Missing required parameters 'xd' and 'timestamp'", 400

    try:
        xd_int = int(xd_value)
    except ValueError:
        return "Invalid XD parameter", 400

    try:
        timestamp_sql = _normalize_change_timestamp(change_timestamp)
    except ValueError:
        return "Invalid timestamp parameter", 400

    sort_column = "t.TIMESTAMP"

    set_variable_sql = f"SET CHANGE_TS = TO_TIMESTAMP_NTZ('{timestamp_sql}')"

    query = f"""
    SELECT
        t.XD,
        t.TIMESTAMP,
        t.TRAVEL_TIME_SECONDS,
        CASE
            WHEN t.TIMESTAMP < $CHANGE_TS THEN 'before'
            ELSE 'after'
        END AS PERIOD
    FROM TRAVEL_TIME_ANALYTICS t
    WHERE t.XD = {xd_int}
      AND t.TIMESTAMP BETWEEN DATEADD('day', -7, $CHANGE_TS)
                          AND DATEADD('day', 7, $CHANGE_TS)
    ORDER BY {sort_column}
    """

    if DEBUG_BACKEND_TIMING:
        print(f"\n[TIMING] /changepoints-detail START")
        print(f"  XD={xd_int}, timestamp={timestamp_sql}")

    def execute_query():
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise Exception("Unable to establish database connection")

        session.sql(set_variable_sql).collect()
        arrow_data = session.sql(query).to_arrow()
        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        result = create_arrow_response(arrow_bytes)
        if DEBUG_BACKEND_TIMING:
            total_time = (time.time() - request_start) * 1000
            print(f"[TIMING] /changepoints-detail COMPLETE in {total_time:.2f}ms")
        return result

    try:
        return handle_auth_error_retry(execute_query)
    except Exception as e:
        print(f"[ERROR] /changepoints-detail: {e}")
        if is_auth_error(e):
            return "Database reconnecting - please wait", 503
        return f"Error fetching changepoint detail data: {e}", 500

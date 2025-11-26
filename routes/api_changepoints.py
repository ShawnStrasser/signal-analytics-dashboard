"""
Changepoints API Routes

Provides aggregated metrics, tabular listings, and detail data for the changepoints
page. Responses use Apache Arrow streams for consistency with the rest of the API.
"""

import time
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, request

from config import DEBUG_BACKEND_TIMING, TIMEZONE, CHANGEPOINT_SEVERITY_THRESHOLD
from database import get_snowflake_session, is_auth_error
from utils.exceptions import InvalidQueryParameter
from utils.arrow_utils import (
    create_arrow_response,
    snowflake_result_to_arrow
)
from utils.error_handler import handle_auth_error_retry
from utils.query_utils import (
    normalize_date,
    build_filter_joins_and_where,
    sanitize_identifier_list,
)

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


def _sanitize_string_list(values, param_name: str = "signal_id"):
    """Validate signal identifier strings before using them in SQL clauses."""
    return sanitize_identifier_list(values, param_name)


def _sanitize_int_list(values):
    """Convert values to integers (as strings) for SQL IN clauses."""
    ints = []
    for val in values or []:
        try:
            ints.append(str(int(val)))
        except (TypeError, ValueError):
            continue
    return ints


_CHANGEPOINT_SEVERITY_SQL = "COALESCE(ABS(t.PCT_CHANGE * t.AVG_DIFF) * 100, 0)"


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


def _default_changepoint_window() -> tuple[str, str]:
    """
    Mirror the frontend changepoint default window:
    end date = today minus 7 days, start date = end minus 21 days.
    """
    zone = _local_zone()
    now = datetime.now(zone) if zone else datetime.utcnow()
    end_date = (now - timedelta(days=7)).date()
    start_date = end_date - timedelta(days=21)
    return start_date.isoformat(), end_date.isoformat()


def _resolve_date_range(start_value, end_value) -> tuple[str, str]:
    """
    Normalize date inputs; on failure, fall back to the default window
    to avoid 500s when filters are cleared or missing.
    """
    try:
        return normalize_date(start_value), normalize_date(end_value)
    except InvalidQueryParameter as exc:
        fallback_start, fallback_end = _default_changepoint_window()
        print(
            f"[WARN] Invalid changepoint date range ({start_value}, {end_value}); "
            f"using default window {fallback_start} to {fallback_end}: {exc}"
        )
        return fallback_start, fallback_end


def _assemble_where_clause(
    start_date,
    end_date,
    filter_where,
    selected_signals=None,
    selected_xds=None,
    *,
    severity_threshold=None
):
    """Compose WHERE clause for changepoint queries."""
    where_parts = [
        f"DATE(t.TIMESTAMP) BETWEEN '{start_date}' AND '{end_date}'"
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

    threshold_value = severity_threshold
    if threshold_value is None or not isinstance(threshold_value, (int, float)):
        threshold_value = CHANGEPOINT_SEVERITY_THRESHOLD
    if threshold_value < 0:
        threshold_value = abs(threshold_value)
    where_parts.append(f"{_CHANGEPOINT_SEVERITY_SQL} >= {threshold_value:.6f}")

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


@changepoints_bp.route('/changepoints-map-signals', methods=['GET', 'POST'])
def get_changepoints_map_signals():
    """Aggregate changepoints by signal for map visualization."""
    request_start = time.time()

    payload = request.get_json(silent=True) if request.method == 'POST' else None

    def _param(name, default=None):
        if request.method == 'POST':
            if not payload:
                return default
            return payload.get(name, default)
        return request.args.get(name, default)

    def _param_list(name):
        if request.method == 'POST':
            if not payload:
                return []
            value = payload.get(name)
            if value is None:
                return []
            if isinstance(value, (list, tuple, set)):
                return list(value)
            return [value]
        return request.args.getlist(name)

    # Base filters
    start_date, end_date = _resolve_date_range(
        _param('start_date'),
        _param('end_date')
    )
    signal_ids = _param_list('signal_ids')
    maintained_by = _param('maintained_by', 'all')
    approach = _param('approach')
    valid_geometry = _param('valid_geometry')

    severity_threshold = _parse_positive_float(
        _param('changepoint_severity_threshold'),
        CHANGEPOINT_SEVERITY_THRESHOLD
    )

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
        severity_threshold=severity_threshold
    )

    query = f"""
    WITH filtered_cp AS (
        SELECT
            t.XD,
            t.TIMESTAMP,
            t.PCT_CHANGE,
            t.AVG_DIFF,
            {_CHANGEPOINT_SEVERITY_SQL} AS SCORE,
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
            SCORE,
            ROW_NUMBER() OVER (
                PARTITION BY SIGNAL_ID
                ORDER BY SCORE DESC, ABS(PCT_CHANGE) DESC, TIMESTAMP DESC
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
        top.BEARING AS TOP_BEARING,
        top.SCORE AS TOP_SCORE
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


@changepoints_bp.route('/changepoints-map-xd', methods=['GET', 'POST'])
def get_changepoints_map_xd():
    """Aggregate changepoints by XD segment for map visualization."""
    request_start = time.time()

    payload = request.get_json(silent=True) if request.method == 'POST' else None

    def _param(name, default=None):
        if request.method == 'POST':
            if not payload:
                return default
            return payload.get(name, default)
        return request.args.get(name, default)

    def _param_list(name):
        if request.method == 'POST':
            if not payload:
                return []
            value = payload.get(name)
            if value is None:
                return []
            if isinstance(value, (list, tuple, set)):
                return list(value)
            return [value]
        return request.args.getlist(name)

    start_date, end_date = _resolve_date_range(
        _param('start_date'),
        _param('end_date')
    )
    signal_ids = _param_list('signal_ids')
    maintained_by = _param('maintained_by', 'all')
    approach = _param('approach')
    valid_geometry = _param('valid_geometry')

    severity_threshold = _parse_positive_float(
        _param('changepoint_severity_threshold'),
        CHANGEPOINT_SEVERITY_THRESHOLD
    )

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
        severity_threshold=severity_threshold
    )

    query = f"""
    WITH filtered_cp AS (
        SELECT
            t.XD,
            t.TIMESTAMP,
            t.PCT_CHANGE,
            t.AVG_DIFF,
            {_CHANGEPOINT_SEVERITY_SQL} AS SCORE,
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
            SCORE,
            ROW_NUMBER() OVER (
                PARTITION BY XD
                ORDER BY SCORE DESC, ABS(PCT_CHANGE) DESC, TIMESTAMP DESC
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
        top.BEARING AS TOP_BEARING,
        top.SCORE AS TOP_SCORE
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


@changepoints_bp.route('/changepoints-table', methods=['GET', 'POST'])
def get_changepoints_table():
    """Return top changepoints (limit 100) for the table with server-side sorting."""
    request_start = time.time()

    payload = request.get_json(silent=True) if request.method == 'POST' else None

    def _param(name, default=None):
        if request.method == 'POST':
            if not payload:
                return default
            return payload.get(name, default)
        return request.args.get(name, default)

    def _param_list(name):
        if request.method == 'POST':
            if not payload:
                return []
            value = payload.get(name)
            if value is None:
                return []
            if isinstance(value, (list, tuple, set)):
                return list(value)
            return [value]
        return request.args.getlist(name)

    # Base filters
    start_date, end_date = _resolve_date_range(
        _param('start_date'),
        _param('end_date')
    )
    signal_ids = _param_list('signal_ids')
    maintained_by = _param('maintained_by', 'all')
    approach = _param('approach')
    valid_geometry = _param('valid_geometry')

    severity_threshold = _parse_positive_float(
        _param('changepoint_severity_threshold'),
        CHANGEPOINT_SEVERITY_THRESHOLD
    )

    selected_signals = _param_list('selected_signals')
    selected_xds = _param_list('selected_xds')

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
        selected_signals=selected_signals,
        selected_xds=selected_xds,
        severity_threshold=severity_threshold
    )

    sort_by = (_param('sort_by', 'score') or 'score').lower()
    sort_dir = (_param('sort_dir', 'desc') or 'desc').lower()

    sort_column_map = {
        'timestamp': 't.TIMESTAMP',
        'pct_change': 't.PCT_CHANGE',
        'avg_diff': 't.AVG_DIFF',
        'score': 'SCORE'
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
        {_CHANGEPOINT_SEVERITY_SQL} AS SCORE,
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

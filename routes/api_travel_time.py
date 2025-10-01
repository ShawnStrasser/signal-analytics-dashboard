"""
Travel Time API Routes - Returns Arrow data directly
Optimized for low-latency small queries
"""

import json
import time
import pyarrow as pa
from flask import Blueprint, request, jsonify

from config import DEBUG_BACKEND_TIMING, DEBUG_DISABLE_SERVER_CACHE
from database import get_snowflake_session
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
    create_xd_lookup_dict,
    get_aggregation_table,
    build_time_of_day_filter
)

travel_time_bp = Blueprint('travel_time', __name__)

# Cache XD geometry since it is static
_xd_geometry_cache = None


@travel_time_bp.route('/signals')
def get_signals():
    """Get signals dimension data as Arrow"""
    session = get_snowflake_session(retry=True, max_retries=2)
    if not session:
        return "Connecting to Database - please wait", 503

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
    FROM DIM_SIGNALS_XD
    """

    try:
        arrow_data = session.sql(query).to_arrow()
        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        return create_arrow_response(arrow_bytes)
    except Exception as e:
        print(f"[ERROR] /signals: {e}")
        return f"Error fetching signals data: {e}", 500


@travel_time_bp.route('/xd-geometry')
def get_xd_geometry():
    """Return XD road segment geometries as GeoJSON FeatureCollection"""
    global _xd_geometry_cache

    # Check cache unless disabled
    if not DEBUG_DISABLE_SERVER_CACHE and _xd_geometry_cache is not None:
        if DEBUG_BACKEND_TIMING:
            print("[TIMING] /xd-geometry: Returned from cache")
        return jsonify(_xd_geometry_cache)

    session = get_snowflake_session(retry=True, max_retries=2)
    if not session:
        return "Connecting to Database - please wait", 503

    query = """
    SELECT
        XD,
        ST_ASGEOJSON(GEOM) AS GEOJSON
    FROM XD_GEOM
    WHERE GEOM IS NOT NULL
    """

    try:
        result = session.sql(query).collect()

        features = []
        for row in result:
            row_dict = row.as_dict() if hasattr(row, 'as_dict') else dict(row)
            geojson_str = row_dict.get('GEOJSON')
            xd_value = row_dict.get('XD')

            if not geojson_str:
                continue

            try:
                geometry = json.loads(geojson_str)
            except json.JSONDecodeError:
                continue

            features.append({
                "type": "Feature",
                "properties": {"XD": xd_value},
                "geometry": geometry
            })

        _xd_geometry_cache = {
            "type": "FeatureCollection",
            "features": features
        }

        return jsonify(_xd_geometry_cache)
    except Exception as e:
        print(f"[ERROR] /xd-geometry: {e}")
        return f"Error fetching XD geometry: {e}", 500


@travel_time_bp.route('/travel-time-summary')
def get_travel_time_summary():
    """Get travel time summary for map visualization as Arrow"""
    request_start = time.time()

    session = get_snowflake_session(retry=True, max_retries=2)
    if not session:
        return "Connecting to Database - please wait", 503

    # Get query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    signal_ids = request.args.getlist('signal_ids')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    start_hour = request.args.get('start_hour')
    end_hour = request.args.get('end_hour')

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    # Determine aggregation table based on date range
    agg_table = get_aggregation_table(start_date_str, end_date_str)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, end_hour)

    if DEBUG_BACKEND_TIMING:
        print(f"\n[TIMING] /travel-time-summary START")
        print(f"  Params: date={start_date_str} to {end_date_str}, signals={len(signal_ids) if signal_ids else 'all'}, table={agg_table}")

    try:
        # Step 1: Query DIM_SIGNALS_XD to get XD segments and signal info
        dim_query_start = time.time()
        dim_query = build_xd_dimension_query(signal_ids, approach, valid_geometry)
        dim_result = session.sql(dim_query).collect()
        dim_query_time = (time.time() - dim_query_start) * 1000

        if DEBUG_BACKEND_TIMING:
            print(f"  [1] DIM_SIGNALS_XD query: {dim_query_time:.2f}ms ({len(dim_result)} rows)")

        if not dim_result:
            if DEBUG_BACKEND_TIMING:
                print(f"  [EARLY EXIT] No dimension results")
            arrow_bytes = create_empty_arrow_response('travel_time_summary')
            return create_arrow_response(arrow_bytes)

        # Extract XD values for analytics query
        extract_start = time.time()
        xd_values = extract_xd_values(dim_result)
        extract_time = (time.time() - extract_start) * 1000

        if DEBUG_BACKEND_TIMING:
            print(f"  [2] Extract XD values: {extract_time:.2f}ms ({len(xd_values)} unique XDs)")

        if not xd_values:
            if DEBUG_BACKEND_TIMING:
                print(f"  [EARLY EXIT] No XD values extracted")
            arrow_bytes = create_empty_arrow_response('travel_time_summary')
            return create_arrow_response(arrow_bytes)

        # Step 2: Query aggregated table using XD values, join with FREEFLOW to calculate TTI
        # ONLY add XD filter if we're filtering to specific signals
        # If no signal_ids were provided, we want ALL XDs
        xd_filter = build_xd_filter(xd_values) if signal_ids else ""

        if DEBUG_BACKEND_TIMING:
            if signal_ids:
                print(f"  [INFO] XD filter applied: {len(xd_values)} XDs")
            else:
                print(f"  [INFO] NO XD filter (querying all signals)")

        # Build query based on aggregation table
        # FIX: Join explosion issue - FREEFLOW should have 1 row per XD
        # We need to GROUP BY first, THEN join with FREEFLOW to avoid multiplying rows
        analytics_query_start = time.time()

        if agg_table == "TRAVEL_TIME_ANALYTICS":
            # Base table: use direct TRAVEL_TIME_SECONDS
            # TTI = (SUM of actual travel times) / (SUM of freeflow times)
            # Each record needs to be divided by its freeflow, then averaged
            analytics_query = f"""
            WITH agg AS (
                SELECT
                    t.XD,
                    SUM(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) as TOTAL_TTI,
                    AVG(t.TRAVEL_TIME_SECONDS) as AVG_TRAVEL_TIME,
                    COUNT(*) as RECORD_COUNT
                FROM TRAVEL_TIME_ANALYTICS t
                INNER JOIN FREEFLOW f ON t.XD = f.XD
                WHERE t.TIMESTAMP >= '{start_date_str}'
                AND t.TIMESTAMP <= '{end_date_str}'
                {xd_filter.replace('XD', 't.XD')}
                {time_filter.replace('HOUR_OF_DAY', 't.HOUR_OF_DAY')}
                GROUP BY t.XD
            )
            SELECT
                XD,
                COALESCE(TOTAL_TTI / NULLIF(RECORD_COUNT, 0), 0) as TRAVEL_TIME_INDEX,
                AVG_TRAVEL_TIME,
                RECORD_COUNT
            FROM agg
            """
        else:
            # Materialized view: use pre-aggregated data
            # TTI = (Total actual travel time) / (Total freeflow time)
            # Total freeflow = record_count * freeflow_per_trip
            date_filter = "DATE_ONLY" if agg_table == "TRAVEL_TIME_DAILY_AGG" else "TIMESTAMP"
            analytics_query = f"""
            SELECT
                mv.XD,
                COALESCE(
                    NULLIF(SUM(mv.TOTAL_TRAVEL_TIME_SECONDS) / NULLIF(SUM(mv.RECORD_COUNT * f.TRAVEL_TIME_SECONDS), 0), 0),
                    0
                ) as TRAVEL_TIME_INDEX,
                SUM(mv.AVG_TRAVEL_TIME * mv.RECORD_COUNT) / NULLIF(SUM(mv.RECORD_COUNT), 0) as AVG_TRAVEL_TIME,
                SUM(mv.RECORD_COUNT) as RECORD_COUNT
            FROM {agg_table} mv
            INNER JOIN FREEFLOW f ON mv.XD = f.XD
            WHERE {date_filter} >= '{start_date_str}'
            AND {date_filter} <= '{end_date_str}'
            {xd_filter.replace('XD', 'mv.XD')}
            {time_filter.replace('HOUR_OF_DAY', 'mv.HOUR_OF_DAY')}
            GROUP BY mv.XD
            """

        analytics_result = session.sql(analytics_query).collect()
        analytics_query_time = (time.time() - analytics_query_start) * 1000

        if DEBUG_BACKEND_TIMING:
            print(f"  [3] Analytics query ({agg_table}): {analytics_query_time:.2f}ms ({len(analytics_result)} rows)")

        # Step 3: Join results - create XD -> analytics lookup
        join_start = time.time()
        analytics_dict = create_xd_lookup_dict(analytics_result)
        join_time = (time.time() - join_start) * 1000

        if DEBUG_BACKEND_TIMING:
            print(f"  [4] Create XD lookup dict: {join_time:.2f}ms")

        # Build final Arrow table
        serialize_start = time.time()
        ids = []
        latitudes = []
        longitudes = []
        approaches = []
        valid_geometries = []
        xds = []
        travel_time_indexes = []
        avg_travel_times = []
        record_counts = []

        for row in dim_result:
            dim_dict = row.as_dict()
            xd = dim_dict['XD']
            analytics = analytics_dict.get(xd, {})

            ids.append(dim_dict['ID'])
            latitudes.append(dim_dict['LATITUDE'])
            longitudes.append(dim_dict['LONGITUDE'])
            approaches.append(dim_dict.get('APPROACH'))
            valid_geometries.append(dim_dict.get('VALID_GEOMETRY'))
            xds.append(xd)
            travel_time_indexes.append(analytics.get('TRAVEL_TIME_INDEX', 0))
            avg_travel_times.append(analytics.get('AVG_TRAVEL_TIME', 0))
            record_counts.append(analytics.get('RECORD_COUNT', 0))

        result_table = pa.table({
            'ID': ids,
            'LATITUDE': latitudes,
            'LONGITUDE': longitudes,
            'APPROACH': approaches,
            'VALID_GEOMETRY': valid_geometries,
            'XD': xds,
            'TRAVEL_TIME_INDEX': travel_time_indexes,
            'AVG_TRAVEL_TIME': avg_travel_times,
            'RECORD_COUNT': record_counts
        })

        arrow_bytes = serialize_arrow_to_ipc(result_table)
        serialize_time = (time.time() - serialize_start) * 1000

        total_time = (time.time() - request_start) * 1000

        if DEBUG_BACKEND_TIMING:
            print(f"  [5] Build Arrow table & serialize: {serialize_time:.2f}ms")
            print(f"  [TOTAL] /travel-time-summary: {total_time:.2f}ms\n")

        return create_arrow_response(arrow_bytes)

    except Exception as e:
        print(f"[ERROR] /travel-time-summary: {e}")
        return f"Error fetching travel time summary: {e}", 500


@travel_time_bp.route('/travel-time-aggregated')
def get_travel_time_aggregated():
    """Get aggregated travel time data by timestamp as Arrow"""
    request_start = time.time()

    session = get_snowflake_session(retry=True, max_retries=2)
    if not session:
        return "Connecting to Database - please wait", 503

    # Get query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    signal_ids = request.args.getlist('signal_ids')
    xd_segments = request.args.getlist('xd_segments')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    start_hour = request.args.get('start_hour')
    end_hour = request.args.get('end_hour')

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    # Determine aggregation table based on date range
    agg_table = get_aggregation_table(start_date_str, end_date_str)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, end_hour)

    if DEBUG_BACKEND_TIMING:
        print(f"\n[TIMING] /travel-time-aggregated START")
        print(f"  Params: date={start_date_str} to {end_date_str}, xd_segments={len(xd_segments) if xd_segments else 0}, signals={len(signal_ids) if signal_ids else 0}, table={agg_table}")

    try:
        # Resolve XD segments if signal_ids provided
        xd_values = None
        if xd_segments:
            xd_values = [int(xd) for xd in xd_segments]
            if DEBUG_BACKEND_TIMING:
                print(f"  [INFO] Using provided XD segments: {len(xd_values)} XDs")
        elif signal_ids:
            # Lookup XD values from dimension table
            dim_query_start = time.time()
            dim_query = build_xd_dimension_query(
                signal_ids, approach, valid_geometry, include_xd_only=True
            )
            dim_result = session.sql(dim_query).collect()
            dim_query_time = (time.time() - dim_query_start) * 1000

            if DEBUG_BACKEND_TIMING:
                print(f"  [1] DIM_SIGNALS_XD query: {dim_query_time:.2f}ms ({len(dim_result)} rows)")

            if not dim_result:
                arrow_bytes = create_empty_arrow_response('travel_time_aggregated')
                return create_arrow_response(arrow_bytes)

            xd_values = extract_xd_values(dim_result)

            if not xd_values:
                arrow_bytes = create_empty_arrow_response('travel_time_aggregated')
                return create_arrow_response(arrow_bytes)
        else:
            # NO signal_ids and NO xd_segments = query all
            if DEBUG_BACKEND_TIMING:
                print(f"  [INFO] NO filters - querying ALL XDs")

        # Build XD filter - only if we have specific XDs to filter
        xd_filter = build_xd_filter(xd_values) if xd_values else ""

        # Build query based on aggregation table
        # FIX: Same join explosion fix - aggregate first, then join FREEFLOW
        query_start = time.time()

        if agg_table == "TRAVEL_TIME_ANALYTICS":
            # Base table: calculate TTI for each record, then aggregate by timestamp
            query = f"""
            SELECT
                t.TIMESTAMP,
                AVG(t.TRAVEL_TIME_SECONDS / f.TRAVEL_TIME_SECONDS) as TRAVEL_TIME_INDEX
            FROM TRAVEL_TIME_ANALYTICS t
            INNER JOIN FREEFLOW f ON t.XD = f.XD
            WHERE t.TIMESTAMP >= '{start_date_str}'
            AND t.TIMESTAMP <= '{end_date_str}'
            {xd_filter.replace('XD', 't.XD')}
            {time_filter.replace('HOUR_OF_DAY', 't.HOUR_OF_DAY')}
            GROUP BY t.TIMESTAMP
            ORDER BY t.TIMESTAMP
            """
        else:
            # Materialized view: use pre-aggregated data
            timestamp_col = "DATE_ONLY" if agg_table == "TRAVEL_TIME_DAILY_AGG" else "TIMESTAMP"
            query = f"""
            SELECT
                mv.{timestamp_col} as TIMESTAMP,
                SUM(mv.TOTAL_TRAVEL_TIME_SECONDS) / NULLIF(SUM(mv.RECORD_COUNT * f.TRAVEL_TIME_SECONDS), 0) as TRAVEL_TIME_INDEX
            FROM {agg_table} mv
            INNER JOIN FREEFLOW f ON mv.XD = f.XD
            WHERE mv.{timestamp_col} >= '{start_date_str}'
            AND mv.{timestamp_col} <= '{end_date_str}'
            {xd_filter.replace('XD', 'mv.XD')}
            {time_filter.replace('HOUR_OF_DAY', 'mv.HOUR_OF_DAY')}
            GROUP BY mv.{timestamp_col}
            ORDER BY mv.{timestamp_col}
            """

        arrow_data = session.sql(query).to_arrow()
        query_time = (time.time() - query_start) * 1000

        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        total_time = (time.time() - request_start) * 1000

        if DEBUG_BACKEND_TIMING:
            print(f"  [2] Aggregated query ({agg_table}): {query_time:.2f}ms")
            print(f"  [TOTAL] /travel-time-aggregated: {total_time:.2f}ms\n")

        return create_arrow_response(arrow_bytes)

    except Exception as e:
        print(f"[ERROR] /travel-time-aggregated: {e}")
        return f"Error fetching aggregated travel time data: {e}", 500

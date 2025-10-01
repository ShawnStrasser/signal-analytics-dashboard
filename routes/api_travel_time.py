"""
Travel Time API Routes - Returns Arrow data directly
Optimized for low-latency small queries
"""

import json
import pyarrow as pa
from flask import Blueprint, request, jsonify

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

    if _xd_geometry_cache is not None:
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

    try:
        # Step 1: Query DIM_SIGNALS_XD to get XD segments and signal info
        dim_query = build_xd_dimension_query(signal_ids, approach, valid_geometry)
        dim_result = session.sql(dim_query).collect()

        if not dim_result:
            arrow_bytes = create_empty_arrow_response('travel_time_summary')
            return create_arrow_response(arrow_bytes)

        # Extract XD values for analytics query
        xd_values = extract_xd_values(dim_result)

        if not xd_values:
            arrow_bytes = create_empty_arrow_response('travel_time_summary')
            return create_arrow_response(arrow_bytes)

        # Step 2: Query aggregated table using XD values, join with FREEFLOW to calculate TTI
        xd_filter = build_xd_filter(xd_values)

        # Build query based on aggregation table
        if agg_table == "TRAVEL_TIME_ANALYTICS":
            # Base table: use direct TRAVEL_TIME_SECONDS
            analytics_query = f"""
            SELECT
                t.XD,
                COALESCE(
                    NULLIF(SUM(t.TRAVEL_TIME_SECONDS) / NULLIF(SUM(f.TRAVEL_TIME_SECONDS), 0), 0),
                    0
                ) as TRAVEL_TIME_INDEX,
                AVG(t.TRAVEL_TIME_SECONDS) as AVG_TRAVEL_TIME,
                COUNT(*) as RECORD_COUNT
            FROM TRAVEL_TIME_ANALYTICS t
            INNER JOIN FREEFLOW f ON t.XD = f.XD
            WHERE t.TIMESTAMP >= '{start_date_str}'
            AND t.TIMESTAMP <= '{end_date_str}'
            {xd_filter.replace('XD', 't.XD')}
            {time_filter.replace('HOUR_OF_DAY', 't.HOUR_OF_DAY')}
            GROUP BY t.XD
            """
        else:
            # Materialized view: use pre-aggregated TOTAL_TRAVEL_TIME_SECONDS and RECORD_COUNT
            date_filter = "mv.DATE_ONLY" if agg_table == "TRAVEL_TIME_DAILY_AGG" else "mv.TIMESTAMP"
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

        # Step 3: Join results - create XD -> analytics lookup
        analytics_dict = create_xd_lookup_dict(analytics_result)

        # Build final Arrow table
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
        return create_arrow_response(arrow_bytes)

    except Exception as e:
        print(f"[ERROR] /travel-time-summary: {e}")
        return f"Error fetching travel time summary: {e}", 500


@travel_time_bp.route('/travel-time-aggregated')
def get_travel_time_aggregated():
    """Get aggregated travel time data by timestamp as Arrow"""
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

    try:
        # Resolve XD segments if signal_ids provided
        xd_values = None
        if xd_segments:
            xd_values = [int(xd) for xd in xd_segments]
        elif signal_ids:
            # Lookup XD values from dimension table
            dim_query = build_xd_dimension_query(
                signal_ids, approach, valid_geometry, include_xd_only=True
            )
            dim_result = session.sql(dim_query).collect()

            if not dim_result:
                arrow_bytes = create_empty_arrow_response('travel_time_aggregated')
                return create_arrow_response(arrow_bytes)

            xd_values = extract_xd_values(dim_result)

            if not xd_values:
                arrow_bytes = create_empty_arrow_response('travel_time_aggregated')
                return create_arrow_response(arrow_bytes)

        # Build XD filter
        xd_filter = build_xd_filter(xd_values) if xd_values else ""

        # Build query based on aggregation table
        if agg_table == "TRAVEL_TIME_ANALYTICS":
            # Base table: use direct TRAVEL_TIME_SECONDS
            query = f"""
            SELECT
                t.TIMESTAMP,
                COALESCE(
                    NULLIF(SUM(t.TRAVEL_TIME_SECONDS) / NULLIF(SUM(f.TRAVEL_TIME_SECONDS), 0), 0),
                    0
                ) as TRAVEL_TIME_INDEX
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
            timestamp_col = "mv.DATE_ONLY as TIMESTAMP" if agg_table == "TRAVEL_TIME_DAILY_AGG" else "mv.TIMESTAMP"
            date_filter = "mv.DATE_ONLY" if agg_table == "TRAVEL_TIME_DAILY_AGG" else "mv.TIMESTAMP"
            query = f"""
            SELECT
                {timestamp_col},
                COALESCE(
                    NULLIF(SUM(mv.TOTAL_TRAVEL_TIME_SECONDS) / NULLIF(SUM(mv.RECORD_COUNT * f.TRAVEL_TIME_SECONDS), 0), 0),
                    0
                ) as TRAVEL_TIME_INDEX
            FROM {agg_table} mv
            INNER JOIN FREEFLOW f ON mv.XD = f.XD
            WHERE {date_filter} >= '{start_date_str}'
            AND {date_filter} <= '{end_date_str}'
            {xd_filter.replace('XD', 'mv.XD')}
            {time_filter.replace('HOUR_OF_DAY', 'mv.HOUR_OF_DAY')}
            GROUP BY {timestamp_col.split(' as ')[0]}
            ORDER BY {timestamp_col.split(' as ')[0]}
            """

        arrow_data = session.sql(query).to_arrow()
        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        return create_arrow_response(arrow_bytes)

    except Exception as e:
        print(f"[ERROR] /travel-time-aggregated: {e}")
        return f"Error fetching aggregated travel time data: {e}", 500

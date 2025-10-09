"""
Anomalies API Routes - Returns Arrow data directly
Optimized for low-latency small queries
"""

import pyarrow as pa
from flask import Blueprint, request

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
    build_xd_filter_with_joins,
    build_filter_joins_and_where,
    create_xd_lookup_dict,
    get_aggregation_table,
    build_time_of_day_filter
)

anomalies_bp = Blueprint('anomalies', __name__)


@anomalies_bp.route('/anomaly-summary')
def get_anomaly_summary():
    """Get anomaly summary data for map visualization as Arrow"""
    session = get_snowflake_session(retry=True, max_retries=2)
    if not session:
        return "Connecting to Database - please wait", 503

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

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    # Determine aggregation table based on date range
    agg_table = get_aggregation_table(start_date_str, end_date_str)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, start_minute, end_hour, end_minute)

    try:
        # Step 1: Determine whether to use join-based or direct filtering
        use_join_based = signal_ids or maintained_by != 'all'

        if use_join_based:
            # Efficient join-based query for large signal selections
            xd_values = build_xd_filter_with_joins(
                session, signal_ids, maintained_by, approach, valid_geometry
            )

            if not xd_values:
                arrow_bytes = create_empty_arrow_response('anomaly_summary')
                return create_arrow_response(arrow_bytes)
        else:
            # No filters - will query all XDs
            xd_values = None

        # Step 1b: Get dimension data for map display (still need lat/lon/approach/etc)
        dim_query = build_xd_dimension_query(signal_ids, approach, valid_geometry)
        dim_result = session.sql(dim_query).collect()

        if not dim_result:
            arrow_bytes = create_empty_arrow_response('anomaly_summary')
            return create_arrow_response(arrow_bytes)

        # Step 2: Query aggregated table using XD values
        xd_filter = build_xd_filter(xd_values) if xd_values else ""

        # Build query based on aggregation table
        if agg_table == "TRAVEL_TIME_ANALYTICS":
            # Base table: count directly
            analytics_query = f"""
            SELECT
                XD,
                COUNT(CASE WHEN ANOMALY = TRUE THEN 1 END) as ANOMALY_COUNT,
                COUNT(CASE WHEN ORIGINATED_ANOMALY = TRUE THEN 1 END) as POINT_SOURCE_COUNT,
                COUNT(*) as RECORD_COUNT
            FROM TRAVEL_TIME_ANALYTICS
            WHERE TIMESTAMP >= '{start_date_str}'
            AND TIMESTAMP <= '{end_date_str}'
            {xd_filter}
            {time_filter}
            GROUP BY XD
            """
        else:
            # Materialized view: sum pre-aggregated counts
            date_filter = "DATE_ONLY" if agg_table == "TRAVEL_TIME_DAILY_AGG" else "TIMESTAMP"
            analytics_query = f"""
            SELECT
                XD,
                SUM(ANOMALY_COUNT) as ANOMALY_COUNT,
                SUM(POINT_SOURCE_COUNT) as POINT_SOURCE_COUNT,
                SUM(RECORD_COUNT) as RECORD_COUNT
            FROM {agg_table}
            WHERE {date_filter} >= '{start_date_str}'
            AND {date_filter} <= '{end_date_str}'
            {xd_filter}
            {time_filter}
            GROUP BY XD
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
        anomaly_counts = []
        point_source_counts = []
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
            anomaly_counts.append(analytics.get('ANOMALY_COUNT', 0))
            point_source_counts.append(analytics.get('POINT_SOURCE_COUNT', 0))
            record_counts.append(analytics.get('RECORD_COUNT', 0))

        result_table = pa.table({
            'ID': ids,
            'LATITUDE': latitudes,
            'LONGITUDE': longitudes,
            'APPROACH': approaches,
            'VALID_GEOMETRY': valid_geometries,
            'XD': xds,
            'ANOMALY_COUNT': anomaly_counts,
            'POINT_SOURCE_COUNT': point_source_counts,
            'RECORD_COUNT': record_counts
        })

        arrow_bytes = serialize_arrow_to_ipc(result_table)
        return create_arrow_response(arrow_bytes)

    except Exception as e:
        print(f"[ERROR] /anomaly-summary: {e}")
        return f"Error fetching anomaly data: {e}", 500


@anomalies_bp.route('/anomaly-aggregated')
def get_anomaly_aggregated():
    """Get aggregated anomaly data by timestamp as Arrow"""
    session = get_snowflake_session(retry=True, max_retries=2)
    if not session:
        return "Connecting to Database - please wait", 503

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

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    # Determine aggregation table based on date range
    agg_table = get_aggregation_table(start_date_str, end_date_str)

    # Build time-of-day filter
    time_filter = build_time_of_day_filter(start_hour, start_minute, end_hour, end_minute)

    try:
        # Resolve XD segments if signal_ids provided
        xd_values = None
        if xd_segments:
            # Map interaction - use direct XD list (small, efficient)
            xd_values = [int(xd) for xd in xd_segments]
        elif signal_ids or maintained_by != 'all':
            # Filter panel - use join-based filtering (efficient for large selections)
            xd_values = build_xd_filter_with_joins(
                session, signal_ids, maintained_by, approach, valid_geometry
            )

            if not xd_values:
                arrow_bytes = create_empty_arrow_response('anomaly_aggregated')
                return create_arrow_response(arrow_bytes)

        # Build XD filter
        xd_filter = build_xd_filter(xd_values) if xd_values else ""

        # Build query based on aggregation table
        if agg_table == "TRAVEL_TIME_ANALYTICS":
            # Base table
            query = f"""
            SELECT
                TIMESTAMP,
                SUM(TRAVEL_TIME_SECONDS) as TOTAL_ACTUAL_TRAVEL_TIME,
                SUM(PREDICTION) as TOTAL_PREDICTION
            FROM TRAVEL_TIME_ANALYTICS
            WHERE TIMESTAMP >= '{start_date_str}'
            AND TIMESTAMP <= '{end_date_str}'
            AND PREDICTION IS NOT NULL
            {xd_filter}
            {time_filter}
            GROUP BY TIMESTAMP
            ORDER BY TIMESTAMP
            """
        else:
            # Materialized view: aggregate using pre-computed sums
            timestamp_col = "CAST(DATE_ONLY AS TIMESTAMP_NTZ) as TIMESTAMP" if agg_table == "TRAVEL_TIME_DAILY_AGG" else "TIMESTAMP"
            date_filter = "DATE_ONLY" if agg_table == "TRAVEL_TIME_DAILY_AGG" else "TIMESTAMP"
            query = f"""
            SELECT
                {timestamp_col},
                SUM(TOTAL_TRAVEL_TIME_SECONDS) as TOTAL_ACTUAL_TRAVEL_TIME,
                SUM(AVG_PREDICTION * RECORD_COUNT) as TOTAL_PREDICTION
            FROM {agg_table}
            WHERE {date_filter} >= '{start_date_str}'
            AND {date_filter} <= '{end_date_str}'
            {xd_filter}
            {time_filter}
            GROUP BY {timestamp_col.split(' as ')[0]}
            ORDER BY {timestamp_col.split(' as ')[0]}
            """

        arrow_data = session.sql(query).to_arrow()
        arrow_bytes = snowflake_result_to_arrow(arrow_data)
        return create_arrow_response(arrow_bytes)

    except Exception as e:
        print(f"[ERROR] /anomaly-aggregated: {e}")
        return f"Error fetching aggregated anomaly data: {e}", 500


@anomalies_bp.route('/travel-time-data')
def get_travel_time_data():
    """Get detailed travel time data for anomaly analysis as Arrow"""
    session = get_snowflake_session(retry=True, max_retries=2)
    if not session:
        return "Connecting to Database - please wait", 503

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

    try:
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

    except Exception as e:
        print(f"[ERROR] /travel-time-data: {e}")
        return f"Error fetching travel time data: {e}", 500

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
    create_xd_lookup_dict
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
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    anomaly_type = request.args.get('anomaly_type', default='All')

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    try:
        # Step 1: Query DIM_SIGNALS_XD to get XD segments and signal info
        dim_query = build_xd_dimension_query(signal_ids, approach, valid_geometry)
        dim_result = session.sql(dim_query).collect()

        if not dim_result:
            arrow_bytes = create_empty_arrow_response('anomaly_summary')
            return create_arrow_response(arrow_bytes)

        # Extract XD values
        xd_values = extract_xd_values(dim_result)

        if not xd_values:
            arrow_bytes = create_empty_arrow_response('anomaly_summary')
            return create_arrow_response(arrow_bytes)

        # Step 2: Query TRAVEL_TIME_ANALYTICS using XD values
        anomaly_filter = ""
        if anomaly_type == "Point Source":
            anomaly_filter = " AND ORIGINATED_ANOMALY = TRUE"
        elif anomaly_type == "All":
            anomaly_filter = " AND ANOMALY = TRUE"

        xd_filter = build_xd_filter(xd_values)
        analytics_query = f"""
        SELECT
            XD,
            COUNT(CASE WHEN ANOMALY = TRUE THEN 1 END) as ANOMALY_COUNT,
            COUNT(CASE WHEN ORIGINATED_ANOMALY = TRUE THEN 1 END) as POINT_SOURCE_COUNT
        FROM TRAVEL_TIME_ANALYTICS
        WHERE TIMESTAMP >= '{start_date_str}'
        AND TIMESTAMP <= '{end_date_str}'
        {anomaly_filter}
        {xd_filter}
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

        result_table = pa.table({
            'ID': ids,
            'LATITUDE': latitudes,
            'LONGITUDE': longitudes,
            'APPROACH': approaches,
            'VALID_GEOMETRY': valid_geometries,
            'XD': xds,
            'ANOMALY_COUNT': anomaly_counts,
            'POINT_SOURCE_COUNT': point_source_counts
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
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    try:
        # Build analytics query - use XD segments directly if provided
        query = f"""
        SELECT
            TIMESTAMP,
            SUM(TRAVEL_TIME_SECONDS) as TOTAL_ACTUAL_TRAVEL_TIME,
            SUM(PREDICTION) as TOTAL_PREDICTION
        FROM TRAVEL_TIME_ANALYTICS
        WHERE TIMESTAMP >= '{start_date_str}'
        AND TIMESTAMP <= '{end_date_str}'
        AND PREDICTION IS NOT NULL
        """

        # Direct XD filter (preferred) or lookup from signal IDs
        if xd_segments:
            xd_filter = build_xd_filter([int(xd) for xd in xd_segments])
            query += xd_filter
        elif signal_ids:
            # Lookup XD values from dimension table
            dim_query = build_xd_dimension_query(
                signal_ids, approach, valid_geometry, include_xd_only=True
            )
            dim_result = session.sql(dim_query).collect()

            if not dim_result:
                arrow_bytes = create_empty_arrow_response('anomaly_aggregated')
                return create_arrow_response(arrow_bytes)

            xd_values = extract_xd_values(dim_result)

            if not xd_values:
                arrow_bytes = create_empty_arrow_response('anomaly_aggregated')
                return create_arrow_response(arrow_bytes)

            xd_filter = build_xd_filter(xd_values)
            query += xd_filter

        query += """
        GROUP BY TIMESTAMP
        ORDER BY TIMESTAMP
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
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')

    # Normalize dates
    start_date_str = normalize_date(start_date)
    end_date_str = normalize_date(end_date)

    try:
        # Step 1: Query DIM_SIGNALS_XD to get XD segments and signal info
        dim_query = build_xd_dimension_query(signal_ids, approach, valid_geometry)

        # Prefer xd_segments if provided
        if xd_segments:
            xd_str = ', '.join(map(str, xd_segments))
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

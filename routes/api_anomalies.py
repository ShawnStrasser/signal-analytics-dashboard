"""
Anomalies API Routes - Returns Arrow data directly
"""

from flask import Blueprint, request
import pandas as pd
from database import get_snowflake_session

anomalies_bp = Blueprint('anomalies', __name__)

@anomalies_bp.route('/anomaly-summary')
def get_anomaly_summary():
    """Get anomaly summary data for map visualization as Arrow"""
    session = get_snowflake_session()
    if not session:
        return "Snowflake connection failed", 500
    
    # Get query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    signal_ids = request.args.getlist('signal_ids')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    anomaly_type = request.args.get('anomaly_type', default='All')
    
    # Normalize dates
    try:
        start_date_str = pd.to_datetime(start_date).strftime('%Y-%m-%d')
        end_date_str = pd.to_datetime(end_date).strftime('%Y-%m-%d')
    except Exception:
        start_date_str = str(start_date)
        end_date_str = str(end_date)
    
    # Step 1: Query DIM_SIGNALS_XD to get XD segments and signal info based on filters
    dim_query = """
    SELECT 
        ID,
        LATITUDE,
        LONGITUDE,
        APPROACH,
        VALID_GEOMETRY,
        XD
    FROM TPAU_DB.TPAU_RITIS_SCHEMA.DIM_SIGNALS_XD
    WHERE LATITUDE IS NOT NULL 
    AND LONGITUDE IS NOT NULL
    """
    
    if signal_ids:
        ids_str = "', '".join(map(str, signal_ids))
        dim_query += f" AND ID IN ('{ids_str}')"
    
    if approach is not None and approach != '':
        # Convert string 'true'/'false' to SQL boolean
        approach_bool = 'TRUE' if approach.lower() == 'true' else 'FALSE'
        dim_query += f" AND APPROACH = {approach_bool}"
        
    if valid_geometry is not None and valid_geometry != '' and valid_geometry != 'all':
        if valid_geometry == 'valid':
            dim_query += " AND VALID_GEOMETRY = TRUE"
        elif valid_geometry == 'invalid':
            dim_query += " AND VALID_GEOMETRY = FALSE"
    
    try:
        # Get the dimension data
        dim_result = session.sql(dim_query).collect()
        
        if not dim_result:
            # No matching signals, return empty result
            import pyarrow as pa
            empty_schema = pa.schema([
                ('ID', pa.string()),
                ('LATITUDE', pa.float64()),
                ('LONGITUDE', pa.float64()),
                ('APPROACH', pa.bool_()),
                ('VALID_GEOMETRY', pa.bool_()),
                ('ANOMALY_COUNT', pa.int64()),
                ('POINT_SOURCE_COUNT', pa.int64())
            ])
            empty_table = pa.table([], schema=empty_schema)
            sink = pa.BufferOutputStream()
            with pa.ipc.new_stream(sink, empty_table.schema) as writer:
                pass
            arrow_bytes = sink.getvalue().to_pybytes()
            return arrow_bytes, 200, {'Content-Type': 'application/octet-stream'}
        
        # Extract XD values
        xd_values = [row.as_dict()['XD'] for row in dim_result if row.as_dict().get('XD')]
        
        if not xd_values:
            # No XD values found
            import pyarrow as pa
            empty_schema = pa.schema([
                ('ID', pa.string()),
                ('LATITUDE', pa.float64()),
                ('LONGITUDE', pa.float64()),
                ('APPROACH', pa.bool_()),
                ('VALID_GEOMETRY', pa.bool_()),
                ('ANOMALY_COUNT', pa.int64()),
                ('POINT_SOURCE_COUNT', pa.int64())
            ])
            empty_table = pa.table([], schema=empty_schema)
            sink = pa.BufferOutputStream()
            with pa.ipc.new_stream(sink, empty_table.schema) as writer:
                pass
            arrow_bytes = sink.getvalue().to_pybytes()
            return arrow_bytes, 200, {'Content-Type': 'application/octet-stream'}
        
        # Step 2: Query TRAVEL_TIME_ANALYTICS directly using XD values
        # Base query for anomaly counts
        anomaly_filter = ""
        if anomaly_type == "Point Source":
            anomaly_filter = " AND ORIGINATED_ANOMALY = TRUE"
        elif anomaly_type == "All":
            anomaly_filter = " AND ANOMALY = TRUE"
        
        xd_str = ', '.join(map(str, xd_values))
        analytics_query = f"""
        SELECT 
            XD,
            COUNT(CASE WHEN ANOMALY = TRUE THEN 1 END) as ANOMALY_COUNT,
            COUNT(CASE WHEN ORIGINATED_ANOMALY = TRUE THEN 1 END) as POINT_SOURCE_COUNT
        FROM TRAVEL_TIME_ANALYTICS
        WHERE TIMESTAMP >= '{start_date_str}'
        AND TIMESTAMP <= '{end_date_str}'
        {anomaly_filter}
        AND XD IN ({xd_str})
        GROUP BY XD
        """
        
        analytics_result = session.sql(analytics_query).collect()
        
        # Step 3: Combine the results in Python
        # Create a dict mapping XD -> analytics data
        analytics_dict = {}
        for row in analytics_result:
            row_dict = row.as_dict()
            analytics_dict[row_dict['XD']] = row_dict
        
        # Build the final result by combining dim and analytics data
        import pyarrow as pa
        ids = []
        latitudes = []
        longitudes = []
        approaches = []
        valid_geometries = []
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
            anomaly_counts.append(analytics.get('ANOMALY_COUNT', 0))
            point_source_counts.append(analytics.get('POINT_SOURCE_COUNT', 0))
        
        result_table = pa.table({
            'ID': ids,
            'LATITUDE': latitudes,
            'LONGITUDE': longitudes,
            'APPROACH': approaches,
            'VALID_GEOMETRY': valid_geometries,
            'ANOMALY_COUNT': anomaly_counts,
            'POINT_SOURCE_COUNT': point_source_counts
        })
        
        # Convert to IPC stream
        batches = result_table.to_batches()
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, result_table.schema) as writer:
            for batch in batches:
                writer.write_batch(batch)
        arrow_bytes = sink.getvalue().to_pybytes()
        return arrow_bytes, 200, {'Content-Type': 'application/octet-stream'}
    except Exception as e:
        return f"Error fetching anomaly data: {e}", 500

@anomalies_bp.route('/anomaly-aggregated')
def get_anomaly_aggregated():
    """Get aggregated anomaly data by timestamp as Arrow"""
    session = get_snowflake_session()
    if not session:
        return "Snowflake connection failed", 500
    
    # Get query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    signal_ids = request.args.getlist('signal_ids')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    
    # Normalize dates
    try:
        start_date_str = pd.to_datetime(start_date).strftime('%Y-%m-%d')
        end_date_str = pd.to_datetime(end_date).strftime('%Y-%m-%d')
    except Exception:
        start_date_str = str(start_date)
        end_date_str = str(end_date)

    # Step 1: Query DIM_SIGNALS_XD to get XD segments based on filters
    dim_query = """
    SELECT XD
    FROM TPAU_DB.TPAU_RITIS_SCHEMA.DIM_SIGNALS_XD
    WHERE LATITUDE IS NOT NULL 
    AND LONGITUDE IS NOT NULL
    """
    
    if signal_ids:
        ids_str = "', '".join(map(str, signal_ids))
        dim_query += f" AND ID IN ('{ids_str}')"
    
    if approach is not None and approach != '':
        # Convert string 'true'/'false' to SQL boolean
        approach_bool = 'TRUE' if approach.lower() == 'true' else 'FALSE'
        dim_query += f" AND APPROACH = {approach_bool}"
        
    if valid_geometry is not None and valid_geometry != '' and valid_geometry != 'all':
        if valid_geometry == 'valid':
            dim_query += " AND VALID_GEOMETRY = TRUE"
        elif valid_geometry == 'invalid':
            dim_query += " AND VALID_GEOMETRY = FALSE"
    
    try:
        # Get the XD segments
        dim_result = session.sql(dim_query).collect()
        
        if not dim_result:
            # No matching signals, return empty result
            import pyarrow as pa
            empty_schema = pa.schema([
                ('TIMESTAMP', pa.timestamp('ns')),
                ('TOTAL_ACTUAL_TRAVEL_TIME', pa.float64()),
                ('TOTAL_PREDICTION', pa.float64())
            ])
            empty_table = pa.table([], schema=empty_schema)
            sink = pa.BufferOutputStream()
            with pa.ipc.new_stream(sink, empty_table.schema) as writer:
                pass
            arrow_bytes = sink.getvalue().to_pybytes()
            return arrow_bytes, 200, {'Content-Type': 'application/octet-stream'}
        
        # Extract XD values
        xd_values = [row.as_dict()['XD'] for row in dim_result if row.as_dict().get('XD')]
        
        if not xd_values:
            # No XD values found
            import pyarrow as pa
            empty_schema = pa.schema([
                ('TIMESTAMP', pa.timestamp('ns')),
                ('TOTAL_ACTUAL_TRAVEL_TIME', pa.float64()),
                ('TOTAL_PREDICTION', pa.float64())
            ])
            empty_table = pa.table([], schema=empty_schema)
            sink = pa.BufferOutputStream()
            with pa.ipc.new_stream(sink, empty_table.schema) as writer:
                pass
            arrow_bytes = sink.getvalue().to_pybytes()
            return arrow_bytes, 200, {'Content-Type': 'application/octet-stream'}
        
        # Step 2: Query TRAVEL_TIME_ANALYTICS directly using XD values
        xd_str = ', '.join(map(str, xd_values))
        query = f"""
        SELECT 
            TIMESTAMP,
            SUM(TRAVEL_TIME_SECONDS) as TOTAL_ACTUAL_TRAVEL_TIME,
            SUM(PREDICTION) as TOTAL_PREDICTION
        FROM TRAVEL_TIME_ANALYTICS
        WHERE TIMESTAMP >= '{start_date_str}'
        AND TIMESTAMP <= '{end_date_str}'
        AND PREDICTION IS NOT NULL
        AND XD IN ({xd_str})
        GROUP BY TIMESTAMP 
        ORDER BY TIMESTAMP
        """
        
        arrow_data = session.sql(query).to_arrow()
        # Convert Arrow table to bytes using proper method
        import pyarrow as pa
        batches = arrow_data.to_batches()
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, arrow_data.schema) as writer:
            for batch in batches:
                writer.write_batch(batch)
        arrow_bytes = sink.getvalue().to_pybytes()
        return arrow_bytes, 200, {'Content-Type': 'application/octet-stream'}
    except Exception as e:
        return f"Error fetching aggregated anomaly data: {e}", 500

@anomalies_bp.route('/travel-time-data')
def get_travel_time_data():
    """Get detailed travel time data for anomaly analysis as Arrow"""
    session = get_snowflake_session()
    if not session:
        return "Snowflake connection failed", 500
    
    # Get query parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    signal_ids = request.args.getlist('signal_ids')
    approach = request.args.get('approach')
    valid_geometry = request.args.get('valid_geometry')
    
    # Normalize dates
    try:
        start_date_str = pd.to_datetime(start_date).strftime('%Y-%m-%d')
        end_date_str = pd.to_datetime(end_date).strftime('%Y-%m-%d')
    except Exception:
        start_date_str = str(start_date)
        end_date_str = str(end_date)

    # Step 1: Query DIM_SIGNALS_XD to get XD segments and signal info based on filters
    dim_query = """
    SELECT 
        ID,
        LATITUDE,
        LONGITUDE,
        APPROACH,
        VALID_GEOMETRY,
        XD
    FROM TPAU_DB.TPAU_RITIS_SCHEMA.DIM_SIGNALS_XD
    WHERE LATITUDE IS NOT NULL 
    AND LONGITUDE IS NOT NULL
    """
    
    if signal_ids:
        ids_str = "', '".join(map(str, signal_ids))
        dim_query += f" AND ID IN ('{ids_str}')"
    
    if approach is not None and approach != '':
        # Convert string 'true'/'false' to SQL boolean
        approach_bool = 'TRUE' if approach.lower() == 'true' else 'FALSE'
        dim_query += f" AND APPROACH = {approach_bool}"
        
    if valid_geometry is not None and valid_geometry != '' and valid_geometry != 'all':
        if valid_geometry == 'valid':
            dim_query += " AND VALID_GEOMETRY = TRUE"
        elif valid_geometry == 'invalid':
            dim_query += " AND VALID_GEOMETRY = FALSE"
    
    try:
        # Get the dimension data
        dim_result = session.sql(dim_query).collect()
        
        if not dim_result:
            # No matching signals, return empty result
            import pyarrow as pa
            empty_schema = pa.schema([
                ('XD', pa.int32()),
                ('TIMESTAMP', pa.timestamp('ns')),
                ('TRAVEL_TIME_SECONDS', pa.float64()),
                ('PREDICTION', pa.float64()),
                ('ANOMALY', pa.bool_()),
                ('ORIGINATED_ANOMALY', pa.bool_()),
                ('ID', pa.string()),
                ('LATITUDE', pa.float64()),
                ('LONGITUDE', pa.float64()),
                ('APPROACH', pa.bool_()),
                ('VALID_GEOMETRY', pa.bool_())
            ])
            empty_table = pa.table([], schema=empty_schema)
            sink = pa.BufferOutputStream()
            with pa.ipc.new_stream(sink, empty_table.schema) as writer:
                pass
            arrow_bytes = sink.getvalue().to_pybytes()
            return arrow_bytes, 200, {'Content-Type': 'application/octet-stream'}
        
        # Extract XD values and create mapping
        xd_to_signal = {}
        for row in dim_result:
            dim_dict = row.as_dict()
            if dim_dict.get('XD'):
                xd_to_signal[dim_dict['XD']] = dim_dict
        
        xd_values = list(xd_to_signal.keys())
        
        if not xd_values:
            # No XD values found
            import pyarrow as pa
            empty_schema = pa.schema([
                ('XD', pa.int32()),
                ('TIMESTAMP', pa.timestamp('ns')),
                ('TRAVEL_TIME_SECONDS', pa.float64()),
                ('PREDICTION', pa.float64()),
                ('ANOMALY', pa.bool_()),
                ('ORIGINATED_ANOMALY', pa.bool_()),
                ('ID', pa.string()),
                ('LATITUDE', pa.float64()),
                ('LONGITUDE', pa.float64()),
                ('APPROACH', pa.bool_()),
                ('VALID_GEOMETRY', pa.bool_())
            ])
            empty_table = pa.table([], schema=empty_schema)
            sink = pa.BufferOutputStream()
            with pa.ipc.new_stream(sink, empty_table.schema) as writer:
                pass
            arrow_bytes = sink.getvalue().to_pybytes()
            return arrow_bytes, 200, {'Content-Type': 'application/octet-stream'}
        
        # Step 2: Query TRAVEL_TIME_ANALYTICS directly using XD values
        xd_str = ', '.join(map(str, xd_values))
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
        AND XD IN ({xd_str})
        ORDER BY TIMESTAMP
        """
        
        analytics_result = session.sql(query).collect()
        
        # Step 3: Combine the results in Python
        import pyarrow as pa
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
        
        # Convert to IPC stream
        batches = result_table.to_batches()
        sink = pa.BufferOutputStream()
        with pa.ipc.new_stream(sink, result_table.schema) as writer:
            for batch in batches:
                writer.write_batch(batch)
        arrow_bytes = sink.getvalue().to_pybytes()
        return arrow_bytes, 200, {'Content-Type': 'application/octet-stream'}
    except Exception as e:
        return f"Error fetching travel time data: {e}", 500
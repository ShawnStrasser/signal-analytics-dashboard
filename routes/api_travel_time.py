"""
Travel Time API Routes - Returns Arrow data directly
"""

import json

from flask import Blueprint, request, jsonify
import pandas as pd
from database import get_snowflake_session

travel_time_bp = Blueprint('travel_time', __name__)

# Cache XD geometry since it is static
_xd_geometry_cache = None

@travel_time_bp.route('/signals')
def get_signals():
    """Get signals dimension data as Arrow"""
    session = get_snowflake_session()
    if not session:
        return "Snowflake connection failed", 500
    
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
    FROM TPAU_DB.TPAU_RITIS_SCHEMA.DIM_SIGNALS_XD
    WHERE LATITUDE IS NOT NULL 
    AND LONGITUDE IS NOT NULL
    """
    
    try:
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
        return f"Error fetching signals data: {e}", 500

@travel_time_bp.route('/xd-geometry')
def get_xd_geometry():
    """Return XD road segment geometries as GeoJSON FeatureCollection"""
    global _xd_geometry_cache

    if _xd_geometry_cache is not None:
        return jsonify(_xd_geometry_cache)

    session = get_snowflake_session()
    if not session:
        return "Snowflake connection failed", 500

    query = """
    SELECT
        XD,
        ST_ASGEOJSON(GEOM) AS GEOJSON
    FROM TPAU_DB.TPAU_RITIS_SCHEMA.XD_GEOM
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
        return f"Error fetching XD geometry: {e}", 500

@travel_time_bp.route('/travel-time-summary')
def get_travel_time_summary():
    """Get travel time summary for map visualization as Arrow"""
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
                ('ID', pa.string()),
                ('LATITUDE', pa.float64()),
                ('LONGITUDE', pa.float64()),
                ('APPROACH', pa.bool_()),
                ('VALID_GEOMETRY', pa.bool_()),
                ('TOTAL_TRAVEL_TIME', pa.float64()),
                ('AVG_TRAVEL_TIME', pa.float64()),
                ('RECORD_COUNT', pa.int64())
            ])
            empty_table = pa.table([], schema=empty_schema)
            sink = pa.BufferOutputStream()
            with pa.ipc.new_stream(sink, empty_table.schema) as writer:
                pass
            arrow_bytes = sink.getvalue().to_pybytes()
            return arrow_bytes, 200, {'Content-Type': 'application/octet-stream'}
        
        # Extract XD values for the next query
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
                ('TOTAL_TRAVEL_TIME', pa.float64()),
                ('AVG_TRAVEL_TIME', pa.float64()),
                ('RECORD_COUNT', pa.int64())
            ])
            empty_table = pa.table([], schema=empty_schema)
            sink = pa.BufferOutputStream()
            with pa.ipc.new_stream(sink, empty_table.schema) as writer:
                pass
            arrow_bytes = sink.getvalue().to_pybytes()
            return arrow_bytes, 200, {'Content-Type': 'application/octet-stream'}
        
        # Step 2: Query TRAVEL_TIME_ANALYTICS directly using XD values
        xd_str = ', '.join(map(str, xd_values))
        analytics_query = f"""
        SELECT 
            XD,
            SUM(TRAVEL_TIME_SECONDS) as TOTAL_TRAVEL_TIME,
            AVG(TRAVEL_TIME_SECONDS) as AVG_TRAVEL_TIME,
            COUNT(*) as RECORD_COUNT
        FROM TRAVEL_TIME_ANALYTICS
        WHERE TIMESTAMP >= '{start_date_str}'
        AND TIMESTAMP <= '{end_date_str}'
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
        total_travel_times = []
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
            total_travel_times.append(analytics.get('TOTAL_TRAVEL_TIME', 0))
            avg_travel_times.append(analytics.get('AVG_TRAVEL_TIME', 0))
            record_counts.append(analytics.get('RECORD_COUNT', 0))
        
        result_table = pa.table({
            'ID': ids,
            'LATITUDE': latitudes,
            'LONGITUDE': longitudes,
            'APPROACH': approaches,
            'VALID_GEOMETRY': valid_geometries,
            'TOTAL_TRAVEL_TIME': total_travel_times,
            'AVG_TRAVEL_TIME': avg_travel_times,
            'RECORD_COUNT': record_counts
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
        return f"Error fetching travel time summary: {e}", 500

@travel_time_bp.route('/travel-time-aggregated')
def get_travel_time_aggregated():
    """Get aggregated travel time data by timestamp as Arrow"""
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
                ('TOTAL_TRAVEL_TIME_SECONDS', pa.float64())
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
                ('TOTAL_TRAVEL_TIME_SECONDS', pa.float64())
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
            SUM(TRAVEL_TIME_SECONDS) as TOTAL_TRAVEL_TIME_SECONDS
        FROM TRAVEL_TIME_ANALYTICS
        WHERE TIMESTAMP >= '{start_date_str}'
        AND TIMESTAMP <= '{end_date_str}'
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
        return f"Error fetching aggregated travel time data: {e}", 500
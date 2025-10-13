"""
Expected Arrow schemas for API endpoint validation
"""

import pyarrow as pa


# Schema for /api/signals endpoint
SIGNALS_SCHEMA = pa.schema([
    pa.field('ID', pa.string()),
    pa.field('LATITUDE', pa.float64()),
    pa.field('LONGITUDE', pa.float64()),
    pa.field('VALID_GEOMETRY', pa.bool_()),
    pa.field('XD', pa.int32()),  # Snowflake returns int32 for INTEGER columns
    pa.field('BEARING', pa.string()),
    pa.field('COUNTY', pa.string()),
    pa.field('ROADNAME', pa.string()),
    pa.field('MILES', pa.float64()),
    pa.field('APPROACH', pa.bool_()),
    pa.field('EXTENDED', pa.bool_())
])


# Schema for /api/dim-signals endpoint
DIM_SIGNALS_SCHEMA = pa.schema([
    pa.field('ID', pa.string()),
    pa.field('DISTRICT', pa.string()),
    pa.field('LATITUDE', pa.float64()),
    pa.field('LONGITUDE', pa.float64()),
    pa.field('ODOT_MAINTAINED', pa.bool_()),
    pa.field('NAME', pa.string())
])


# Schema for /api/xd-geometry endpoint
XD_GEOMETRY_SCHEMA = pa.schema([
    pa.field('XD', pa.int32()),
    pa.field('GEOJSON', pa.string())
])


# Schema for /api/travel-time-summary endpoint
TRAVEL_TIME_SUMMARY_SCHEMA = pa.schema([
    pa.field('ID', pa.string()),
    pa.field('LATITUDE', pa.float64()),
    pa.field('LONGITUDE', pa.float64()),
    pa.field('APPROACH', pa.bool_()),
    pa.field('VALID_GEOMETRY', pa.bool_()),
    pa.field('XD', pa.int32()),
    pa.field('TRAVEL_TIME_INDEX', pa.float64()),
    pa.field('AVG_TRAVEL_TIME', pa.float64()),
    pa.field('RECORD_COUNT', pa.int32())
])


# Schema for /api/travel-time-aggregated endpoint (without legend)
TRAVEL_TIME_AGGREGATED_SCHEMA = pa.schema([
    pa.field('TIMESTAMP', pa.timestamp('ns')),
    pa.field('TRAVEL_TIME_INDEX', pa.float64())
])


# Schema for /api/travel-time-aggregated endpoint (with legend)
TRAVEL_TIME_AGGREGATED_LEGEND_SCHEMA = pa.schema([
    pa.field('TIMESTAMP', pa.timestamp('ns')),
    pa.field('LEGEND_GROUP', pa.string()),
    pa.field('TRAVEL_TIME_INDEX', pa.float64())
])


# Schema for /api/travel-time-by-time-of-day endpoint (without legend)
TRAVEL_TIME_BY_TOD_SCHEMA = pa.schema([
    pa.field('TIME_OF_DAY', pa.time64('ns')),
    pa.field('TRAVEL_TIME_INDEX', pa.float64())
])


# Schema for /api/travel-time-by-time-of-day endpoint (with legend)
TRAVEL_TIME_BY_TOD_LEGEND_SCHEMA = pa.schema([
    pa.field('TIME_OF_DAY', pa.time64('ns')),
    pa.field('LEGEND_GROUP', pa.string()),
    pa.field('TRAVEL_TIME_INDEX', pa.float64())
])


def validate_schema(table: pa.Table, expected_schema: pa.Schema, allow_empty: bool = False) -> bool:
    """
    Validate that an Arrow table matches the expected schema.

    Args:
        table: PyArrow table to validate
        expected_schema: Expected schema
        allow_empty: If True, allow empty tables (0 rows)

    Returns:
        True if schema matches, raises AssertionError otherwise
    """
    # Check that all expected fields are present
    actual_field_names = set(table.schema.names)
    expected_field_names = set(expected_schema.names)

    assert actual_field_names == expected_field_names, \
        f"Schema mismatch. Expected fields: {expected_field_names}, Got: {actual_field_names}"

    # Check field types (allowing for nullable differences and timestamp precision)
    for field in expected_schema:
        actual_field = table.schema.field(field.name)
        expected_type = field.type
        actual_type = actual_field.type

        # Special handling for timestamps - accept any precision
        if pa.types.is_timestamp(expected_type):
            assert pa.types.is_timestamp(actual_type), \
                f"Type mismatch for field {field.name}: expected timestamp, got {actual_type}"
        # Special handling for times - accept any precision
        elif pa.types.is_time(expected_type):
            assert pa.types.is_time(actual_type), \
                f"Type mismatch for field {field.name}: expected time, got {actual_type}"
        # Special handling for floating point - accept float64, decimal, or integer (SQL AVG can return int for empty sets)
        elif pa.types.is_floating(expected_type):
            assert pa.types.is_floating(actual_type) or pa.types.is_decimal(actual_type) or pa.types.is_integer(actual_type), \
                f"Type mismatch for field {field.name}: expected float/decimal/int, got {actual_type}"
        # Special handling for integers - accept any integer width
        elif pa.types.is_integer(expected_type):
            assert pa.types.is_integer(actual_type), \
                f"Type mismatch for field {field.name}: expected integer, got {actual_type}"
        # For other types, must match exactly
        else:
            assert actual_type == expected_type, \
                f"Type mismatch for field {field.name}: expected {expected_type}, got {actual_type}"

    # Check for data presence unless empty is allowed
    if not allow_empty:
        assert table.num_rows > 0, "Table is empty but data was expected"

    return True


def validate_non_empty(table: pa.Table) -> bool:
    """Validate that table has at least one row"""
    assert table.num_rows > 0, "Table is empty"
    return True


def validate_can_be_empty(table: pa.Table) -> bool:
    """Validate that table can be empty (always passes, used for clarity)"""
    return True

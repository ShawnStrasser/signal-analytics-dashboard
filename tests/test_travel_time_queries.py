"""
Integration tests for Travel Time API database queries.

Tests validate that all endpoint/filter combinations return valid Arrow data
with correct schemas from Snowflake.
"""

import pytest
from tests.schemas import (
    SIGNALS_SCHEMA,
    DIM_SIGNALS_SCHEMA,
    XD_GEOMETRY_SCHEMA,
    TRAVEL_TIME_SUMMARY_SCHEMA,
    TRAVEL_TIME_AGGREGATED_SCHEMA,
    TRAVEL_TIME_AGGREGATED_LEGEND_SCHEMA,
    TRAVEL_TIME_BY_TOD_SCHEMA,
    TRAVEL_TIME_BY_TOD_LEGEND_SCHEMA,
    validate_schema
)


# =============================================================================
# STATIC ENDPOINT TESTS (no parameters)
# =============================================================================

@pytest.mark.integration
def test_signals_endpoint(client, arrow_deserializer):
    """Test /api/signals returns all signal data"""
    response = client.get('/api/signals')

    # Allow 503 if database is connecting
    assert response.status_code in [200, 503], f"Unexpected status: {response.status_code}"

    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, SIGNALS_SCHEMA, allow_empty=False)
        assert table.num_rows > 0, "Expected signal data"


@pytest.mark.integration
def test_dim_signals_endpoint(client, arrow_deserializer):
    """Test /api/dim-signals returns hierarchical filter data"""
    response = client.get('/api/dim-signals')

    assert response.status_code in [200, 503], f"Unexpected status: {response.status_code}"

    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, DIM_SIGNALS_SCHEMA, allow_empty=False)
        assert table.num_rows > 0, "Expected DIM_SIGNALS data"


@pytest.mark.integration
def test_xd_geometry_endpoint(client, arrow_deserializer):
    """Test /api/xd-geometry returns road segment geometries"""
    response = client.get('/api/xd-geometry')

    assert response.status_code in [200, 503], f"Unexpected status: {response.status_code}"

    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, XD_GEOMETRY_SCHEMA, allow_empty=False)
        assert table.num_rows > 0, "Expected geometry data"


# =============================================================================
# TRAVEL TIME SUMMARY TESTS
# =============================================================================

@pytest.mark.integration
def test_summary_baseline_3day(client, arrow_deserializer, date_ranges):
    """Test summary with 3-day range, no other filters"""
    start, end = date_ranges['3day']
    response = client.get(f'/api/travel-time-summary?start_date={start}&end_date={end}')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_SUMMARY_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_summary_signal_filter_7day(client, arrow_deserializer, date_ranges, sample_signal_ids):
    """Test summary with 7-day range + signal_ids filter"""
    start, end = date_ranges['7day']
    signal_params = '&'.join([f'signal_ids={sid}' for sid in sample_signal_ids])
    response = client.get(f'/api/travel-time-summary?start_date={start}&end_date={end}&{signal_params}')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_SUMMARY_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_summary_maintained_odot_30day(client, arrow_deserializer, date_ranges):
    """Test summary with 30-day range + maintained_by=odot filter"""
    start, end = date_ranges['30day']
    response = client.get(f'/api/travel-time-summary?start_date={start}&end_date={end}&maintained_by=odot')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_SUMMARY_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_summary_approach_true_1day(client, arrow_deserializer, date_ranges):
    """Test summary with 1-day range + approach=true filter"""
    start, end = date_ranges['1day']
    response = client.get(f'/api/travel-time-summary?start_date={start}&end_date={end}&approach=true')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_SUMMARY_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_summary_valid_geometry_1day(client, arrow_deserializer, date_ranges):
    """Test summary with 1-day range + valid_geometry=valid filter"""
    start, end = date_ranges['1day']
    response = client.get(f'/api/travel-time-summary?start_date={start}&end_date={end}&valid_geometry=valid')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_SUMMARY_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_summary_time_of_day_1day(client, arrow_deserializer, date_ranges):
    """Test summary with 1-day range + time_of_day filter (6am-7pm)"""
    start, end = date_ranges['1day']
    response = client.get(
        f'/api/travel-time-summary?start_date={start}&end_date={end}'
        f'&start_hour=6&start_minute=0&end_hour=19&end_minute=0'
    )

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_SUMMARY_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_summary_day_of_week_1day(client, arrow_deserializer, date_ranges):
    """Test summary with 1-day range + day_of_week filter (weekdays)"""
    start, end = date_ranges['1day']
    dow_params = '&'.join([f'day_of_week={d}' for d in [1, 2, 3, 4, 5]])
    response = client.get(f'/api/travel-time-summary?start_date={start}&end_date={end}&{dow_params}')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_SUMMARY_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_summary_xd_segments_1day(client, arrow_deserializer, date_ranges, sample_xd_segments):
    """Test summary with 1-day range + xd_segments (map selection)"""
    start, end = date_ranges['1day']
    xd_params = '&'.join([f'xd_segments={xd}' for xd in sample_xd_segments])
    response = client.get(f'/api/travel-time-summary?start_date={start}&end_date={end}&{xd_params}')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_SUMMARY_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_summary_multi_combo_1day(client, arrow_deserializer, date_ranges, sample_signal_ids):
    """Test summary with 1-day range + signal_ids + time_of_day + day_of_week"""
    start, end = date_ranges['1day']
    signal_params = '&'.join([f'signal_ids={sid}' for sid in sample_signal_ids])
    dow_params = '&'.join([f'day_of_week={d}' for d in [1, 2, 3, 4, 5]])

    response = client.get(
        f'/api/travel-time-summary?start_date={start}&end_date={end}'
        f'&{signal_params}&{dow_params}'
        f'&start_hour=6&start_minute=0&end_hour=19&end_minute=0'
    )

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_SUMMARY_SCHEMA, allow_empty=True)


# =============================================================================
# TRAVEL TIME AGGREGATED TESTS
# =============================================================================

@pytest.mark.integration
def test_aggregated_baseline_3day(client, arrow_deserializer, date_ranges):
    """Test aggregated with 3-day range (no aggregation), no other filters"""
    start, end = date_ranges['3day']
    response = client.get(f'/api/travel-time-aggregated?start_date={start}&end_date={end}')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_AGGREGATED_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_aggregated_signal_filter_7day(client, arrow_deserializer, date_ranges, sample_signal_ids):
    """Test aggregated with 7-day range (hourly agg) + signal_ids filter"""
    start, end = date_ranges['7day']
    signal_params = '&'.join([f'signal_ids={sid}' for sid in sample_signal_ids])
    response = client.get(f'/api/travel-time-aggregated?start_date={start}&end_date={end}&{signal_params}')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_AGGREGATED_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_aggregated_maintained_odot_30day(client, arrow_deserializer, date_ranges):
    """Test aggregated with 30-day range (daily agg) + maintained_by=odot filter"""
    start, end = date_ranges['30day']
    response = client.get(f'/api/travel-time-aggregated?start_date={start}&end_date={end}&maintained_by=odot')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_AGGREGATED_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_aggregated_approach_true_1day(client, arrow_deserializer, date_ranges):
    """Test aggregated with 1-day range + approach=true filter"""
    start, end = date_ranges['1day']
    response = client.get(f'/api/travel-time-aggregated?start_date={start}&end_date={end}&approach=true')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_AGGREGATED_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_aggregated_valid_geometry_1day(client, arrow_deserializer, date_ranges):
    """Test aggregated with 1-day range + valid_geometry=valid filter"""
    start, end = date_ranges['1day']
    response = client.get(f'/api/travel-time-aggregated?start_date={start}&end_date={end}&valid_geometry=valid')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_AGGREGATED_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_aggregated_time_of_day_1day(client, arrow_deserializer, date_ranges):
    """Test aggregated with 1-day range + time_of_day filter (6am-7pm)"""
    start, end = date_ranges['1day']
    response = client.get(
        f'/api/travel-time-aggregated?start_date={start}&end_date={end}'
        f'&start_hour=6&start_minute=0&end_hour=19&end_minute=0'
    )

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_AGGREGATED_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_aggregated_day_of_week_1day(client, arrow_deserializer, date_ranges):
    """Test aggregated with 1-day range + day_of_week filter (weekdays)"""
    start, end = date_ranges['1day']
    dow_params = '&'.join([f'day_of_week={d}' for d in [1, 2, 3, 4, 5]])
    response = client.get(f'/api/travel-time-aggregated?start_date={start}&end_date={end}&{dow_params}')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_AGGREGATED_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_aggregated_xd_segments_1day(client, arrow_deserializer, date_ranges, sample_xd_segments):
    """Test aggregated with 1-day range + xd_segments (map selection)"""
    start, end = date_ranges['1day']
    xd_params = '&'.join([f'xd_segments={xd}' for xd in sample_xd_segments])
    response = client.get(f'/api/travel-time-aggregated?start_date={start}&end_date={end}&{xd_params}')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_AGGREGATED_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_aggregated_legend_county_1day(client, arrow_deserializer, date_ranges):
    """Test aggregated with 1-day range + legend_by=county"""
    start, end = date_ranges['1day']
    response = client.get(f'/api/travel-time-aggregated?start_date={start}&end_date={end}&legend_by=county')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_AGGREGATED_LEGEND_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_aggregated_multi_combo_1day(client, arrow_deserializer, date_ranges, sample_signal_ids):
    """Test aggregated with 1-day range + signal_ids + time_of_day + day_of_week"""
    start, end = date_ranges['1day']
    signal_params = '&'.join([f'signal_ids={sid}' for sid in sample_signal_ids])
    dow_params = '&'.join([f'day_of_week={d}' for d in [1, 2, 3, 4, 5]])

    response = client.get(
        f'/api/travel-time-aggregated?start_date={start}&end_date={end}'
        f'&{signal_params}&{dow_params}'
        f'&start_hour=6&start_minute=0&end_hour=19&end_minute=0'
    )

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_AGGREGATED_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_aggregated_xd_legend_combo_1day(client, arrow_deserializer, date_ranges, sample_xd_segments):
    """Test aggregated with 1-day range + xd_segments + legend_by=county"""
    start, end = date_ranges['1day']
    xd_params = '&'.join([f'xd_segments={xd}' for xd in sample_xd_segments])
    response = client.get(
        f'/api/travel-time-aggregated?start_date={start}&end_date={end}'
        f'&{xd_params}&legend_by=county'
    )

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_AGGREGATED_LEGEND_SCHEMA, allow_empty=True)


# =============================================================================
# TRAVEL TIME BY TIME-OF-DAY TESTS
# =============================================================================

@pytest.mark.integration
def test_time_of_day_baseline_1day(client, arrow_deserializer, date_ranges):
    """Test time-of-day with 1-day range, no other filters"""
    start, end = date_ranges['1day']
    response = client.get(f'/api/travel-time-by-time-of-day?start_date={start}&end_date={end}')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_BY_TOD_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_time_of_day_signal_filter_1day(client, arrow_deserializer, date_ranges, sample_signal_ids):
    """Test time-of-day with 1-day range + signal_ids filter"""
    start, end = date_ranges['1day']
    signal_params = '&'.join([f'signal_ids={sid}' for sid in sample_signal_ids])
    response = client.get(f'/api/travel-time-by-time-of-day?start_date={start}&end_date={end}&{signal_params}')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_BY_TOD_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_time_of_day_maintained_odot_1day(client, arrow_deserializer, date_ranges):
    """Test time-of-day with 1-day range + maintained_by=odot filter"""
    start, end = date_ranges['1day']
    response = client.get(f'/api/travel-time-by-time-of-day?start_date={start}&end_date={end}&maintained_by=odot')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_BY_TOD_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_time_of_day_time_filter_1day(client, arrow_deserializer, date_ranges):
    """Test time-of-day with 1-day range + time filter (6am-7pm)"""
    start, end = date_ranges['1day']
    response = client.get(
        f'/api/travel-time-by-time-of-day?start_date={start}&end_date={end}'
        f'&start_hour=6&start_minute=0&end_hour=19&end_minute=0'
    )

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_BY_TOD_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_time_of_day_day_of_week_1day(client, arrow_deserializer, date_ranges):
    """Test time-of-day with 1-day range + day_of_week filter (weekdays)"""
    start, end = date_ranges['1day']
    dow_params = '&'.join([f'day_of_week={d}' for d in [1, 2, 3, 4, 5]])
    response = client.get(f'/api/travel-time-by-time-of-day?start_date={start}&end_date={end}&{dow_params}')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_BY_TOD_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_time_of_day_xd_segments_1day(client, arrow_deserializer, date_ranges, sample_xd_segments):
    """Test time-of-day with 1-day range + xd_segments (map selection)"""
    start, end = date_ranges['1day']
    xd_params = '&'.join([f'xd_segments={xd}' for xd in sample_xd_segments])
    response = client.get(f'/api/travel-time-by-time-of-day?start_date={start}&end_date={end}&{xd_params}')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_BY_TOD_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_time_of_day_legend_bearing_1day(client, arrow_deserializer, date_ranges):
    """Test time-of-day with 1-day range + legend_by=bearing"""
    start, end = date_ranges['1day']
    response = client.get(f'/api/travel-time-by-time-of-day?start_date={start}&end_date={end}&legend_by=bearing')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_BY_TOD_LEGEND_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_time_of_day_multi_combo_1day(client, arrow_deserializer, date_ranges, sample_xd_segments):
    """Test time-of-day with 1-day range + xd_segments + day_of_week + legend_by"""
    start, end = date_ranges['1day']
    xd_params = '&'.join([f'xd_segments={xd}' for xd in sample_xd_segments])
    dow_params = '&'.join([f'day_of_week={d}' for d in [1, 2, 3, 4, 5]])

    response = client.get(
        f'/api/travel-time-by-time-of-day?start_date={start}&end_date={end}'
        f'&{xd_params}&{dow_params}&legend_by=bearing'
    )

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_BY_TOD_LEGEND_SCHEMA, allow_empty=True)


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

@pytest.mark.integration
def test_edge_case_empty_result(client, arrow_deserializer, date_ranges):
    """Test that empty results return valid schema (non-existent signal ID)"""
    start, end = date_ranges['1day']
    response = client.get(f'/api/travel-time-summary?start_date={start}&end_date={end}&signal_ids=NONEXISTENT999')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        # Should have correct schema even if empty
        validate_schema(table, TRAVEL_TIME_SUMMARY_SCHEMA, allow_empty=True)


@pytest.mark.integration
def test_edge_case_maintained_others(client, arrow_deserializer, date_ranges):
    """Test maintained_by=others filter works correctly"""
    start, end = date_ranges['1day']
    response = client.get(f'/api/travel-time-summary?start_date={start}&end_date={end}&maintained_by=others')

    assert response.status_code in [200, 503]
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        validate_schema(table, TRAVEL_TIME_SUMMARY_SCHEMA, allow_empty=True)

# Database Query Integration Tests

Comprehensive integration tests for Travel Time API endpoints that validate database queries against Snowflake.

## Overview

This test suite validates that all Travel Time API endpoints return valid Arrow data with correct schemas when queried with different filter combinations. Tests use real database connections and verify end-to-end query execution.

## Test Coverage

- **30 integration tests** covering all major parameter combinations
- **3 static endpoints**: `/signals`, `/dim-signals`, `/xd-geometry`
- **3 data endpoints**: `/travel-time-summary`, `/travel-time-aggregated`, `/travel-time-by-time-of-day`

### Parameters Tested

Each data endpoint is tested with strategic combinations of:

- **Date ranges**: 1 day, 3 days (no agg), 7 days (hourly agg), 30 days (daily agg)
- **Signal filters**: specific signal IDs, maintained_by (odot/others)
- **Geometry filters**: approach (true/false), valid_geometry (valid/invalid)
- **Time filters**: time_of_day (6am-7pm), day_of_week (weekdays)
- **Map selection**: XD segments (from map clicks)
- **Legend grouping**: county, bearing (for chart legends)
- **Multi-combinations**: multiple filters applied together

## Requirements

Install test dependencies:

```bash
pip install pytest pytest-flask pytest-xdist
```

Or install from requirements.txt:

```bash
pip install -r requirements.txt
```

## Running Tests

### Run all tests

```bash
pytest tests/test_travel_time_queries.py -v
```

### Run specific test categories

```bash
# Static endpoints only
pytest tests/test_travel_time_queries.py -k "signals or dim_signals or geometry" -v

# Summary endpoint tests
pytest tests/test_travel_time_queries.py -k "summary" -v

# Aggregated endpoint tests
pytest tests/test_travel_time_queries.py -k "aggregated" -v

# Time-of-day endpoint tests
pytest tests/test_travel_time_queries.py -k "time_of_day" -v

# Edge cases only
pytest tests/test_travel_time_queries.py -k "edge_case" -v
```

### Run with parallel execution (faster)

```bash
pytest tests/test_travel_time_queries.py -v -n auto
```

### Run with timing information

```bash
pytest tests/test_travel_time_queries.py -v --durations=10
```

### Run only integration tests

```bash
pytest tests/test_travel_time_queries.py -m integration -v
```

## Test Strategy

Tests use **combined parameters** to minimize test count while maximizing coverage:

- Each test validates **one unique parameter combination**
- If a test fails, the specific parameter causing the issue is identified
- Date ranges are distributed across tests (no dedicated date range tests)
- All tests use **yesterday's date as reference** for consistency

### Diagnostic Approach

When a test fails, you can identify the issue by:

1. **Endpoint name** - which API endpoint has the problem
2. **Test name** - which parameter combination failed
3. **Compare with baseline** - isolate the specific parameter by comparing with simpler tests

Example: If `test_aggregated_legend_county_1day` fails but `test_aggregated_baseline_3day` passes, the issue is with legend grouping logic.

## Test Fixtures

Defined in `conftest.py`:

- `client` - Flask test client for API requests
- `yesterday` - Yesterday's date as reference point
- `date_ranges` - Pre-calculated date ranges (1d, 3d, 7d, 30d)
- `sample_signal_ids` - Real signal IDs from database
- `sample_xd_segments` - Real XD segments from database
- `arrow_deserializer` - Function to deserialize Arrow responses

## Schema Validation

All responses are validated against expected Arrow schemas defined in `schemas.py`:

- Field names must match exactly
- Field types must match exactly
- Empty results are allowed (return valid schema with 0 rows)
- Non-empty results must have at least 1 row

## Database Connection

Tests require an active Snowflake connection. The test suite uses the same connection method as the main application:

1. Active session (preferred): `get_active_session()`
2. Connection parameters: `SNOWFLAKE_CONNECTION` environment variable

If database is unavailable, tests will return 503 status and be skipped.

## Expected Test Results

- **All tests should pass** when database is available
- **Status codes**: 200 (success) or 503 (database connecting)
- **Empty results**: Valid for some filter combinations (e.g., non-existent signal ID)
- **Non-empty results**: Expected for most filter combinations with real data

## Troubleshooting

### Tests fail with connection errors

Ensure Snowflake connection is configured:
- Active session is available, OR
- `SNOWFLAKE_CONNECTION` environment variable is set

### Tests fail with schema mismatches

Check if database schema has changed:
- Update schemas in `tests/schemas.py`
- Verify API endpoints return expected fields

### Tests timeout or run slowly

Use parallel execution:
```bash
pytest tests/test_travel_time_queries.py -n auto
```

Or run specific categories instead of all tests.

## File Structure

```
tests/
├── __init__.py                      # Package marker
├── README.md                        # This file
├── conftest.py                      # Pytest fixtures and configuration
├── schemas.py                       # Expected Arrow schemas
└── test_travel_time_queries.py      # Main test suite (30 tests)
```

## Future Enhancements

Potential additions:

- Anomalies API endpoint tests
- Performance benchmarking tests
- Data volume validation tests
- Query optimization tests

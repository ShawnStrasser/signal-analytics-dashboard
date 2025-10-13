"""
Pytest configuration and fixtures for database query tests
"""

import pytest
import pyarrow as pa
from datetime import datetime, timedelta
from flask import Flask
from app import app as flask_app


@pytest.fixture(scope="session")
def app():
    """Create Flask app for testing"""
    flask_app.config.update({
        "TESTING": True,
    })
    yield flask_app


@pytest.fixture(scope="session")
def client(app):
    """Create Flask test client"""
    return app.test_client()


@pytest.fixture(scope="session")
def yesterday():
    """Get yesterday's date as YYYY-MM-DD string"""
    return (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


@pytest.fixture(scope="session")
def date_ranges(yesterday):
    """
    Generate date ranges based on yesterday as the end date.
    Returns dict with keys: '1day', '3day', '7day', '30day'
    Each value is a tuple: (start_date, end_date)
    """
    end_date = datetime.strptime(yesterday, '%Y-%m-%d')

    return {
        '1day': (end_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')),
        '3day': ((end_date - timedelta(days=2)).strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')),
        '7day': ((end_date - timedelta(days=6)).strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')),
        '30day': ((end_date - timedelta(days=29)).strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    }


@pytest.fixture(scope="session")
def test_signal_ids():
    """Sample signal IDs for testing - these should exist in your database"""
    # These are example IDs - adjust based on your actual data
    return ['1001', '1002', '1003']


@pytest.fixture(scope="session")
def test_xd_segments():
    """Sample XD segments for testing - these should exist in your database"""
    # These will be populated from the first test or you can hardcode known values
    # For now, return None and the tests will fetch real XDs from /signals endpoint
    return None


def deserialize_arrow_response(response_data: bytes) -> pa.Table:
    """
    Deserialize Arrow IPC stream from HTTP response.

    Args:
        response_data: Raw bytes from HTTP response

    Returns:
        PyArrow Table
    """
    reader = pa.ipc.open_stream(response_data)
    return reader.read_all()


@pytest.fixture(scope="session")
def arrow_deserializer():
    """Fixture that provides Arrow deserialization function"""
    return deserialize_arrow_response


@pytest.fixture(scope="session")
def sample_xd_segments(client, arrow_deserializer):
    """
    Fetch a small sample of XD segments from the database for testing.
    This runs once per test session.
    """
    response = client.get('/api/signals')
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        # Get first 5 XD segments
        xd_list = table['XD'].to_pylist()[:5]
        return xd_list
    return []


@pytest.fixture(scope="session")
def sample_signal_ids(client, arrow_deserializer):
    """
    Fetch a small sample of signal IDs from the database for testing.
    This runs once per test session.
    """
    response = client.get('/api/dim-signals')
    if response.status_code == 200:
        table = arrow_deserializer(response.data)
        # Get first 3 signal IDs
        id_list = table['ID'].to_pylist()[:3]
        return id_list
    return []


def pytest_configure(config):
    """Configure pytest with custom markers"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )

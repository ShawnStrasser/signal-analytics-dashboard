import pyarrow as pa
import pytest

import app as app_module
from routes import api_before_after


class _FakeQueryResult:
    def to_arrow(self):
        return pa.table({"VALUE": pa.array([], type=pa.int8())})


class _FakeSession:
    def __init__(self):
        self.queries = []

    def sql(self, query):
        self.queries.append(query)
        return _FakeQueryResult()


@pytest.fixture
def before_after_route_harness(monkeypatch):
    session = _FakeSession()

    monkeypatch.setattr(app_module.captcha_sessions, 'is_verified', lambda request: True)
    monkeypatch.setattr(api_before_after, 'handle_auth_error_retry', lambda query_func: query_func())
    monkeypatch.setattr(api_before_after, 'get_snowflake_session', lambda retry=True, max_retries=2: session)
    monkeypatch.setattr(api_before_after, 'snowflake_result_to_arrow', lambda arrow_table: b'arrow-bytes')
    monkeypatch.setattr(
        api_before_after,
        'create_arrow_response',
        lambda data, status=200: (data, status, {'Content-Type': 'application/octet-stream'})
    )
    monkeypatch.setattr(api_before_after, 'is_auth_error', lambda error: False)

    return session


def _build_before_after_params():
    return {
        'before_start_date': '2026-03-31',
        'before_end_date': '2026-04-06',
        'after_start_date': '2026-04-07',
        'after_end_date': '2026-04-13',
    }


def _assert_signal_filter_applied(session):
    assert session.queries, 'Expected the endpoint to execute a Snowflake query.'
    assert "s.ID IN ('C-7205', 'C-7206')" in session.queries[-1]


@pytest.mark.parametrize(
    'endpoint',
    [
        '/api/before-after-summary',
        '/api/before-after-summary-xd',
        '/api/before-after-aggregated',
        '/api/before-after-by-time-of-day',
    ],
)
def test_before_after_endpoints_accept_comma_separated_signal_ids(
    client,
    before_after_route_harness,
    endpoint,
):
    response = client.get(
        endpoint,
        query_string={
            **_build_before_after_params(),
            'signal_ids': 'C-7205,C-7206',
        },
    )

    assert response.status_code == 200
    _assert_signal_filter_applied(before_after_route_harness)


@pytest.mark.parametrize(
    'endpoint',
    [
        '/api/before-after-summary',
        '/api/before-after-summary-xd',
        '/api/before-after-aggregated',
        '/api/before-after-by-time-of-day',
    ],
)
def test_before_after_endpoints_accept_post_signal_id_arrays(
    client,
    before_after_route_harness,
    endpoint,
):
    response = client.post(
        endpoint,
        json={
            **_build_before_after_params(),
            'signal_ids': ['C-7205', 'C-7206'],
        },
    )

    assert response.status_code == 200
    _assert_signal_filter_applied(before_after_route_harness)
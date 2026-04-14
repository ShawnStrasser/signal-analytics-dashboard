import pytest

import app as app_module
from routes import api_anomalies, api_before_after, api_changepoints, api_travel_time


def _dummy_session():
    return object()


def _patch_route_execution(monkeypatch, module):
    monkeypatch.setattr(module, 'handle_auth_error_retry', lambda query_func: query_func(), raising=False)
    monkeypatch.setattr(module, 'get_snowflake_session', lambda retry=True, max_retries=2: _dummy_session(), raising=False)
    monkeypatch.setattr(module, 'is_auth_error', lambda error: False, raising=False)


@pytest.fixture(autouse=True)
def _disable_captcha(monkeypatch):
    monkeypatch.setattr(app_module.captcha_sessions, 'is_verified', lambda request: True)


@pytest.mark.parametrize(
    ('module', 'endpoint', 'params'),
    [
        (api_travel_time, '/api/travel-time-summary', {'start_date': '2026-04-01', 'end_date': '2026-04-02'}),
        (api_travel_time, '/api/travel-time-summary-xd', {'start_date': '2026-04-01', 'end_date': '2026-04-02'}),
        (api_travel_time, '/api/travel-time-aggregated', {'start_date': '2026-04-01', 'end_date': '2026-04-02'}),
        (api_travel_time, '/api/travel-time-by-time-of-day', {'start_date': '2026-04-01', 'end_date': '2026-04-02'}),
        (api_travel_time, '/api/travel-time-data', {'start_date': '2026-04-01', 'end_date': '2026-04-02'}),
        (api_anomalies, '/api/anomaly-summary', {'start_date': '2026-04-01', 'end_date': '2026-04-02'}),
        (api_anomalies, '/api/anomaly-summary-xd', {'start_date': '2026-04-01', 'end_date': '2026-04-02'}),
        (api_anomalies, '/api/anomaly-aggregated', {'start_date': '2026-04-01', 'end_date': '2026-04-02'}),
        (api_anomalies, '/api/anomaly-by-time-of-day', {'start_date': '2026-04-01', 'end_date': '2026-04-02'}),
        (api_anomalies, '/api/anomaly-percent-aggregated', {'start_date': '2026-04-01', 'end_date': '2026-04-02'}),
        (api_anomalies, '/api/anomaly-percent-by-time-of-day', {'start_date': '2026-04-01', 'end_date': '2026-04-02'}),
        (api_before_after, '/api/before-after-summary', {
            'before_start_date': '2026-03-31',
            'before_end_date': '2026-04-06',
            'after_start_date': '2026-04-07',
            'after_end_date': '2026-04-13',
        }),
        (api_before_after, '/api/before-after-summary-xd', {
            'before_start_date': '2026-03-31',
            'before_end_date': '2026-04-06',
            'after_start_date': '2026-04-07',
            'after_end_date': '2026-04-13',
        }),
        (api_before_after, '/api/before-after-aggregated', {
            'before_start_date': '2026-03-31',
            'before_end_date': '2026-04-06',
            'after_start_date': '2026-04-07',
            'after_end_date': '2026-04-13',
        }),
        (api_before_after, '/api/before-after-by-time-of-day', {
            'before_start_date': '2026-03-31',
            'before_end_date': '2026-04-06',
            'after_start_date': '2026-04-07',
            'after_end_date': '2026-04-13',
        }),
        (api_changepoints, '/api/changepoints-map-signals', {'start_date': '2026-03-10', 'end_date': '2026-04-01'}),
        (api_changepoints, '/api/changepoints-map-xd', {'start_date': '2026-03-10', 'end_date': '2026-04-01'}),
        (api_changepoints, '/api/changepoints-table', {'start_date': '2026-03-10', 'end_date': '2026-04-01'}),
    ],
)
def test_invalid_signal_ids_return_400_not_500(client, monkeypatch, module, endpoint, params):
    _patch_route_execution(monkeypatch, module)

    response = client.get(
        endpoint,
        query_string={
            **params,
            'signal_ids': 'BAD$ID',
        },
    )

    assert response.status_code == 400
    assert response.get_json() == {'error': 'Invalid signal_id value.'}


@pytest.mark.parametrize(
    'endpoint',
    [
        '/api/changepoints-map-signals',
        '/api/changepoints-map-xd',
        '/api/changepoints-table',
    ],
)
def test_changepoint_routes_accept_comma_separated_get_signal_ids(client, monkeypatch, endpoint):
    _patch_route_execution(monkeypatch, api_changepoints)

    captured = {}

    def fake_execute_arrow_query(query):
        captured['query'] = query
        return b'arrow-bytes', 200, {'Content-Type': 'application/octet-stream'}

    monkeypatch.setattr(api_changepoints, '_execute_arrow_query', fake_execute_arrow_query)

    response = client.get(
        endpoint,
        query_string={
            'start_date': '2026-03-10',
            'end_date': '2026-04-01',
            'signal_ids': 'C-7205,C-7206',
        },
    )

    assert response.status_code == 200
    assert "'C-7205', 'C-7206'" in captured['query']


def test_monitoring_route_accepts_comma_separated_get_lists(client, monkeypatch):
    _patch_route_execution(monkeypatch, api_anomalies)

    captured = {}

    def fake_fetch_monitoring_anomaly_rows(filters):
        captured['filters'] = filters
        return [], 4.0

    monkeypatch.setattr(api_anomalies, 'fetch_monitoring_anomaly_rows', fake_fetch_monitoring_anomaly_rows)

    response = client.get(
        '/api/monitoring-anomalies',
        query_string={
            'start_date': '2026-04-01',
            'end_date': '2026-04-02',
            'signal_ids': 'C-7205,C-7206',
            'selected_signals': 'C-7205,C-7206',
            'selected_xds': '101,102',
            'selected_signal_groups': 'District1,District2',
        },
    )

    assert response.status_code == 200
    assert captured['filters']['signal_ids'] == ['C-7205', 'C-7206']
    assert captured['filters']['selected_signals'] == ['C-7205', 'C-7206']
    assert captured['filters']['selected_xds'] == ['101', '102']
    assert captured['filters']['selected_signal_groups'] == ['District1', 'District2']
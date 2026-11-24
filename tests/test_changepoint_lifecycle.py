"""Changepoint lifecycle: temporary changepoints hidden, enduring filter, report sections."""

from datetime import datetime, timedelta

import pytest

import app as app_module
from routes import api_changepoints
from services import report_service


DATES = {'start_date': '2026-11-15', 'end_date': '2026-11-16'}

ENDPOINTS = [
    '/api/changepoints-map-signals',
    '/api/changepoints-map-xd',
    '/api/changepoints-table',
]


@pytest.fixture(autouse=True)
def _disable_captcha(monkeypatch):
    monkeypatch.setattr(app_module.captcha_sessions, 'is_verified', lambda request: True)


@pytest.fixture
def captured_route_query(monkeypatch):
    captured = {}

    def fake_execute_arrow_query(query):
        captured['query'] = query
        return b'arrow-bytes', 200, {'Content-Type': 'application/octet-stream'}

    monkeypatch.setattr(api_changepoints, 'handle_auth_error_retry', lambda fn: fn())
    monkeypatch.setattr(api_changepoints, '_execute_arrow_query', fake_execute_arrow_query)
    return captured


def _get(client, endpoint, **extra):
    return client.get(
        endpoint,
        query_string={'start_date': '2026-10-01', 'end_date': '2026-10-21', **extra},
    )


@pytest.mark.parametrize('endpoint', ENDPOINTS)
def test_routes_always_hide_temporary_changepoints(client, captured_route_query, endpoint):
    response = _get(client, endpoint)
    assert response.status_code == 200
    query = captured_route_query['query']
    assert 'COALESCE(t.IS_ENDURING, TRUE)' in query
    assert 't.IS_ENDURING = TRUE' not in query
    assert 'IS_CHANGEPOINT' not in query


@pytest.mark.parametrize('endpoint', ENDPOINTS)
def test_routes_enduring_only_filter(client, captured_route_query, endpoint):
    response = _get(client, endpoint, changepoint_type='enduring')
    assert response.status_code == 200
    query = captured_route_query['query']
    assert 'COALESCE(t.IS_ENDURING, TRUE)' in query
    assert 't.IS_ENDURING = TRUE' in query


@pytest.mark.parametrize('endpoint', ENDPOINTS)
def test_routes_new_filter_and_unknown_values(client, captured_route_query, endpoint):
    _get(client, endpoint, changepoint_type='new')
    assert 'COALESCE(t.IS_CHANGEPOINT, TRUE)' in captured_route_query['query']

    _get(client, endpoint, changepoint_type="enduring'; DROP TABLE x;--")
    query = captured_route_query['query']
    assert 'DROP TABLE' not in query
    assert 't.IS_ENDURING = TRUE' not in query


def test_table_returns_is_enduring_column(client, captured_route_query):
    _get(client, '/api/changepoints-table')
    assert 't.IS_ENDURING,' in captured_route_query['query']


class _FakeArrow:
    num_rows = 0


class _FakeSession:
    def __init__(self, rows=None):
        self.queries = []
        self._rows = rows or []

    def sql(self, query):
        self.queries.append(query)
        return self

    def to_arrow(self):
        return _FakeArrow()

    def collect(self):
        return list(self._rows)


def test_detail_window_params_are_clamped(client, monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(api_changepoints, 'handle_auth_error_retry', lambda fn: fn())
    monkeypatch.setattr(api_changepoints, 'get_snowflake_session', lambda retry=True, max_retries=2: session)
    monkeypatch.setattr(api_changepoints, 'snowflake_result_to_arrow', lambda table: b'arrow-bytes')

    client.get('/api/changepoints-detail', query_string={'xd': '123', 'timestamp': '2026-10-01T08:00:00'})
    assert "DATEADD('day', -7," in session.queries[-1]
    assert "DATEADD('day', 7," in session.queries[-1]

    client.get('/api/changepoints-detail', query_string={
        'xd': '123', 'timestamp': '2026-10-01T08:00:00', 'days_before': '14', 'days_after': '21',
    })
    assert "DATEADD('day', -14," in session.queries[-1]
    assert "DATEADD('day', 21," in session.queries[-1]

    client.get('/api/changepoints-detail', query_string={
        'xd': '123', 'timestamp': '2026-10-01T08:00:00', 'days_before': '9999', 'days_after': 'abc',
    })
    assert "DATEADD('day', -60," in session.queries[-1]
    assert "DATEADD('day', 7," in session.queries[-1]


def _report_row(**overrides):
    row = {
        'XD': 101, 'TIMESTAMP': datetime(2026, 11, 2, 8, 0), 'PCT_CHANGE': 0.2, 'AVG_DIFF': 10.0,
        'AVG_BEFORE': 50.0, 'AVG_AFTER': 60.0, 'SCORE': 200.0, 'IS_CHANGEPOINT': None,
        'IS_ENDURING': None, 'ENDURING_DATE': None, 'BASELINE_TT': None, 'BEFORE_TT': None,
        'AFTER_TT': None, 'ENDURING_TT': None, 'ROADNAME': 'Main St', 'BEARING': 'NB',
        'ASSOCIATED_SIGNALS': '1001',
    }
    row.update(overrides)
    return row


def _patch_report_session(monkeypatch, rows=None):
    session = _FakeSession(rows)
    monkeypatch.setattr(report_service, 'handle_auth_error_retry', lambda fn: fn())
    monkeypatch.setattr(report_service, 'get_snowflake_session', lambda retry=True, max_retries=2: session)
    return session


def test_fetch_new_changepoints_query(monkeypatch):
    session = _patch_report_session(monkeypatch, [_report_row()])
    rows = report_service.fetch_monitoring_rows(DATES, kind='new')
    query = session.queries[-1]
    assert "DATEADD(day, -9, DATE_TRUNC('day', CURRENT_TIMESTAMP()))" in query
    assert 'COALESCE(t.IS_CHANGEPOINT, TRUE)' in query
    assert 'COALESCE(t.IS_ENDURING, TRUE)' in query
    assert 'LIMIT 10' in query
    # Legacy rows (NULL lifecycle columns) still come through as new changepoints
    assert rows[0]['kind'] == 'new'
    assert rows[0]['is_enduring'] is None


def test_fetch_enduring_changepoints_query(monkeypatch):
    session = _patch_report_session(monkeypatch, [_report_row(IS_CHANGEPOINT=False, IS_ENDURING=True, ENDURING_TT=61.0)])
    rows = report_service.fetch_monitoring_rows(DATES, kind='enduring')
    query = session.queries[-1]
    assert 't.IS_ENDURING = TRUE' in query
    assert "DATEADD(day, -22, DATE_TRUNC('day', CURRENT_TIMESTAMP()))" in query
    # Enduring rows without a stage-1 alert must still be reported
    assert 'IS_CHANGEPOINT, TRUE' not in query
    assert rows[0]['kind'] == 'enduring'
    assert rows[0]['enduring_tt'] == 61.0


def test_fetch_monitoring_rows_rejects_unknown_kind(monkeypatch):
    _patch_report_session(monkeypatch)
    with pytest.raises(ValueError):
        report_service.fetch_monitoring_rows(DATES, kind='temporary')


def _patch_report_pipeline(monkeypatch, *, new_rows, enduring_rows, anomaly_rows):
    sent = {}

    def fake_fetch(filters, limit=10, *, kind='new'):
        return list(new_rows if kind == 'new' else enduring_rows)

    def fake_send(email, subject, html, attachments=None):
        sent.update(email=email, subject=subject, html=html, attachments=attachments)

    monkeypatch.setattr(report_service, 'fetch_monitoring_rows', fake_fetch)
    monkeypatch.setattr(report_service, 'fetch_monitoring_anomaly_rows', lambda filters: (list(anomaly_rows), 4.0))
    monkeypatch.setattr(report_service, 'enrich_monitoring_rows', lambda rows, **kw: [dict(r, window=kw) for r in rows])
    monkeypatch.setattr(report_service, 'build_monitoring_pdf', lambda *a, **kw: b'%PDF-fake')
    monkeypatch.setattr(report_service.joke_service, 'prepare_joke', lambda report_date: None)
    monkeypatch.setattr(report_service.email_service, 'send_email', fake_send)
    monkeypatch.setattr(report_service, 'DEBUG_SAVE_REPORT_PDF', False)
    return sent


def test_report_with_only_enduring_changepoints_is_sent(monkeypatch):
    sent = _patch_report_pipeline(
        monkeypatch,
        new_rows=[],
        enduring_rows=[{'xd': 5, 'timestamp': datetime(2026, 11, 2), 'kind': 'enduring'}],
        anomaly_rows=[],
    )
    result = report_service.generate_and_send_report('someone@example.gov', DATES)
    assert result['sent'] is True
    assert result['changepoints'] == 0
    assert result['rows'] == 0
    assert result['enduring_changepoints'] == 1
    assert result['anomalies'] == 0
    assert '0 new changepoints' in sent['html']
    assert '1 enduring changepoint<' in sent['html']
    assert 'Nov 24, 2026' in sent['html']


def test_report_without_any_rows_is_not_sent(monkeypatch):
    sent = _patch_report_pipeline(monkeypatch, new_rows=[], enduring_rows=[], anomaly_rows=[])
    result = report_service.generate_and_send_report('someone@example.gov', DATES)
    assert result == {'sent': False, 'reason': 'no_data', 'email': 'someone@example.gov'}
    assert sent == {}


def test_enduring_rows_use_longer_chart_window(monkeypatch):
    captured = {}

    def fake_pdf(filters, rows, **kwargs):
        captured['new'] = list(rows)
        captured['enduring'] = list(kwargs['enduring_rows'])
        return b'%PDF-fake'

    _patch_report_pipeline(
        monkeypatch,
        new_rows=[{'xd': 1, 'timestamp': datetime(2026, 11, 15)}],
        enduring_rows=[{'xd': 2, 'timestamp': datetime(2026, 11, 2)}],
        anomaly_rows=[],
    )
    monkeypatch.setattr(report_service, 'build_monitoring_pdf', fake_pdf)
    report_service.generate_and_send_report('someone@example.gov', DATES)
    assert captured['new'][0]['window'] == {'days_before': 7, 'days_after': 7}
    assert captured['enduring'][0]['window'] == {'days_before': 14, 'days_after': 21}


def _synthetic_enriched_row(xd, change_ts, *, kind, days_before, days_after, shift):
    hourly = []
    detail = []
    start = change_ts - timedelta(days=days_before)
    for hour in range(int((days_before + days_after) * 24)):
        ts = start + timedelta(hours=hour)
        period = 'before' if ts < change_ts else 'after'
        value = 60 + 15 * ((hour % 24) in range(7, 10)) + (shift if period == 'after' else 0)
        hourly.append({'timestamp': ts, 'travel_time_seconds': float(value), 'period': period})
        for quarter in range(4):
            detail.append({'timestamp': ts + timedelta(minutes=15 * quarter), 'travel_time_seconds': float(value), 'period': period})
    date_series = report_service.build_changepoint_date_series(hourly)
    time_series = report_service.build_changepoint_time_of_day_series(detail)
    row = {
        'xd': xd, 'timestamp': change_ts, 'pct_change': shift / 60, 'avg_diff': float(shift),
        'avg_before': 60.0, 'avg_after': 60.0 + shift, 'score': 100.0, 'severity_score': 100.0,
        'roadname': 'Main St', 'bearing': 'NB', 'associated_signals': '1001', 'kind': kind,
        'before_tt': 61.0, 'after_tt': 61.0 + shift, 'enduring_tt': 60.5 + shift,
        'date_series': date_series, 'time_series': time_series,
    }
    row['chart_images'] = report_service._collect_chart_images(row, date_series, time_series)
    return row


def test_build_monitoring_pdf_renders_both_changepoint_sections():
    pytest.importorskip('fpdf')
    pytest.importorskip('matplotlib')
    new_row = _synthetic_enriched_row(1, datetime(2026, 11, 15, 8), kind='new', days_before=7, days_after=7, shift=8)
    enduring_row = _synthetic_enriched_row(2, datetime(2026, 11, 2, 8), kind='enduring', days_before=14, days_after=21, shift=-6)
    pdf_bytes = report_service.build_monitoring_pdf(
        {}, [new_row], enduring_rows=[enduring_row], report_date=datetime(2026, 11, 24).date()
    )
    assert pdf_bytes.startswith(b'%PDF')

    only_enduring = report_service.build_monitoring_pdf(
        {}, [], enduring_rows=[enduring_row], report_date=datetime(2026, 11, 24).date()
    )
    assert only_enduring.startswith(b'%PDF')

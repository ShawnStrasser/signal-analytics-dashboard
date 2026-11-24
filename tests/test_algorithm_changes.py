"""INRIX algorithm changes (detected from CHANGEPOINTS), report section filtering, report_date windows."""

from datetime import date, datetime

import pytest

import app as app_module
from routes import api_changepoints
from services import algorithm_changes, report_service


OCT_EVENT = {
    'EVENT_DATE': date(2026, 10, 22), 'PEAK_TIMESTAMP': datetime(2026, 10, 22, 14, 30),
    'START_DATE': date(2026, 10, 21), 'END_DATE': date(2026, 10, 22),
    'PEAK_HOUR_SEGMENTS': 289, 'SEGMENTS': 1099, 'SHARE_SLOWER': 0.91548,
}
SEP_EVENT = {
    'EVENT_DATE': date(2026, 9, 29), 'PEAK_TIMESTAMP': datetime(2026, 9, 29, 11, 30),
    'START_DATE': date(2026, 9, 29), 'END_DATE': date(2026, 9, 29),
    'PEAK_HOUR_SEGMENTS': 149, 'SEGMENTS': 483, 'SHARE_SLOWER': 0.604555,
}


def _events(*rows):
    return [algorithm_changes._normalize_row(row) for row in rows]


class _Session:
    """Fake Snowpark session: the detection query returns events, anything else returns rows."""

    def __init__(self, *, events=None, rows=None):
        self.queries = []
        self.events = events or []
        self.rows = rows
        self._current = None

    def sql(self, query):
        self.queries.append(query)
        self._current = query
        return self

    def collect(self):
        if 'MAX_BY(TIMESTAMP, N)' in self._current:
            return list(self.events)
        return list(self.rows or [])


@pytest.fixture(autouse=True)
def _fresh_cache():
    algorithm_changes.clear_cache()
    yield
    algorithm_changes.clear_cache()


@pytest.fixture(autouse=True)
def _disable_captcha(monkeypatch):
    monkeypatch.setattr(app_module.captcha_sessions, 'is_verified', lambda request: True)


def _patch_session(monkeypatch, session):
    monkeypatch.setattr(algorithm_changes, 'handle_auth_error_retry', lambda fn: fn())
    monkeypatch.setattr(algorithm_changes, 'get_snowflake_session', lambda retry=True, max_retries=2: session)


# --------------------------------------------------------------------------- lookup

def test_fetch_detects_events_from_changepoints_and_caches(monkeypatch):
    session = _Session(events=[SEP_EVENT, OCT_EVENT])
    _patch_session(monkeypatch, session)

    events = algorithm_changes.fetch_algorithm_changes()
    assert [e['event_date'] for e in events] == [date(2026, 9, 29), date(2026, 10, 22)]
    assert events[1]['peak_timestamp'] == datetime(2026, 10, 22, 14, 30)
    assert events[1]['segments'] == 1099

    query = session.queries[0]
    assert 'FROM CHANGEPOINTS WHERE COALESCE(IS_CHANGEPOINT, TRUE)' in query
    assert 'ALGORITHM_CHANGES' not in query
    assert 'e.PEAK >= 80' in query          # 80+ segments with a changepoint within one hour
    assert 'd.PEAK >= 25' in query          # adjacent days join the span at 25+

    # Second call (any range) is served from the in-process cache
    algorithm_changes.fetch_algorithm_changes('2026-10-01', '2026-10-31')
    assert len(session.queries) == 1
    # ...unless the cache is bypassed
    algorithm_changes.fetch_algorithm_changes(use_cache=False)
    assert len(session.queries) == 2


def test_fetch_raises_when_query_fails(monkeypatch):
    class _Broken(_Session):
        def collect(self):
            raise RuntimeError('warehouse suspended')

    _patch_session(monkeypatch, _Broken())
    with pytest.raises(RuntimeError):
        algorithm_changes.fetch_algorithm_changes()


@pytest.mark.parametrize('start,end,expected', [
    ('2026-10-01', '2026-10-20', []),                      # ends before the event
    ('2026-10-22', '2026-10-30', [date(2026, 10, 22)]),    # starts on the last event day
    ('2026-10-15', '2026-10-21', [date(2026, 10, 22)]),    # ends on the first event day
    ('2026-09-01', '2026-11-30', [date(2026, 9, 29), date(2026, 10, 22)]),  # spans both
    (None, '2026-10-01', [date(2026, 9, 29)]),
    ('2026-10-23', None, []),
])
def test_filter_overlapping(start, end, expected):
    events = _events(SEP_EVENT, OCT_EVENT)
    result = algorithm_changes.filter_overlapping(events, start, end)
    assert [e['event_date'] for e in result] == expected


def test_serialize_event_carries_local_offset():
    payload = algorithm_changes.serialize_event(_events(OCT_EVENT)[0])
    assert payload['start_date'] == '2026-10-21'
    assert payload['end_date'] == '2026-10-22'
    assert payload['peak_local'] == '2026-10-22T14:30:00'
    assert payload['peak_timestamp'] == '2026-10-22T14:30:00-07:00'


# --------------------------------------------------------------------------- report impact

def test_report_impact_for_report_inside_event():
    impact = algorithm_changes.report_impact(date(2026, 10, 31), _events(SEP_EVENT, OCT_EVENT))
    assert impact['section_days'] == {
        'anomalies': date(2026, 10, 30), 'new': date(2026, 10, 22), 'enduring': date(2026, 10, 9),
    }
    assert list(impact['excluded']) == ['new']
    assert impact['notes'] == [
        'INRIX algorithm change on Oct 22, 2026 (~1,100 segments shifted at 2:30 PM). '
        'New changepoints from Oct 21–22 omitted.'
    ]
    assert impact['excluded_text']['new'] == 'Omitted: INRIX algorithm change on Oct 21–22, 2026.'

    plain = algorithm_changes.report_impact(date(2026, 10, 31), _events(OCT_EVENT), dash='-')
    assert 'Oct 21-22' in plain['notes'][0]
    assert all(ord(ch) < 128 for ch in plain['notes'][0])


def test_report_impact_names_every_affected_section():
    # R = 2026-10-23: anomalies day 10/22 is inside the event; new (10/14) and enduring (10/1) are not
    impact = algorithm_changes.report_impact(date(2026, 10, 23), _events(OCT_EVENT))
    assert list(impact['excluded']) == ['anomalies']
    assert impact['notes'][0].endswith('Anomalies from Oct 21–22 omitted.')

    # R = 2026-10-21 + 22 days = 2026-11-12/13: enduring day inside the event
    impact = algorithm_changes.report_impact(date(2026, 11, 13), _events(OCT_EVENT))
    assert list(impact['excluded']) == ['enduring']
    assert impact['notes'][0].endswith('Enduring changepoints from Oct 21–22 omitted.')


def test_report_impact_without_events():
    impact = algorithm_changes.report_impact(date(2026, 11, 24), [])
    assert impact['excluded'] == {}
    assert impact['notes'] == []


def test_report_impact_survives_lookup_failure(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError('no access')

    monkeypatch.setattr(algorithm_changes, 'fetch_algorithm_changes', broken)
    impact = algorithm_changes.report_impact(date(2026, 10, 31))
    assert impact['excluded'] == {}
    assert impact['error'] == 'no access'


def test_text_helpers():
    assert algorithm_changes.approx_count(1099) == '1,100'
    assert algorithm_changes.approx_count(483) == '480'
    assert algorithm_changes.approx_count(42) == '42'
    assert algorithm_changes.format_clock(datetime(2026, 1, 1, 0, 5)) == '12:05 AM'
    assert algorithm_changes.format_clock(datetime(2026, 1, 1, 12, 0)) == '12:00 PM'
    cross_month = {'start_date': date(2026, 10, 31), 'end_date': date(2026, 11, 1)}
    assert algorithm_changes.format_span(cross_month, '-') == 'Oct 31-Nov 1, 2026'


# --------------------------------------------------------------------------- report_date windows

def test_enduring_clause_requires_not_alerted_earlier():
    clauses = report_service._monitoring_kind_clauses('enduring', date(2026, 11, 24))
    assert 't.IS_ENDURING = TRUE' in clauses
    assert 't.IS_CHANGEPOINT = FALSE' in clauses
    assert "t.TIMESTAMP >= '2026-11-02'" in clauses
    assert "t.TIMESTAMP < '2026-11-03'" in clauses


def test_enduring_reported_clause_lists_changepoints_alerted_earlier():
    clauses = report_service._monitoring_kind_clauses('enduring_reported', date(2026, 11, 24))
    assert 't.IS_ENDURING = TRUE' in clauses
    assert 'COALESCE(t.IS_CHANGEPOINT, TRUE)' in clauses
    assert "t.TIMESTAMP >= '2026-11-02'" in clauses
    assert "t.TIMESTAMP < '2026-11-03'" in clauses


def test_new_clause_window_for_past_report_date():
    clauses = report_service._monitoring_kind_clauses('new', date(2026, 10, 31))
    assert "t.TIMESTAMP >= '2026-10-22'" in clauses
    assert "t.TIMESTAMP < '2026-10-23'" in clauses
    assert 'COALESCE(t.IS_CHANGEPOINT, TRUE)' in clauses


def test_anomaly_query_uses_day_before_report_date(monkeypatch):
    session = _Session(rows=[{
        'XD': 7, 'ROADNAME': 'Main St', 'BEARING': 'NB', 'ASSOCIATED_SIGNALS': '1001',
        'TOTAL_SAMPLES': 96, 'ANOMALY_SAMPLES': 20, 'TOTAL_EXCESS_SECONDS': 600.0, 'SEVERITY_SCORE': 43.0,
    }])
    monkeypatch.setattr(report_service, 'handle_auth_error_retry', lambda fn: fn())
    monkeypatch.setattr(report_service, 'get_snowflake_session', lambda retry=True, max_retries=2: session)

    rows, _ = report_service.fetch_monitoring_anomaly_rows(
        {'start_date': '2026-10-22', 'end_date': '2026-10-22'}, report_date=date(2026, 10, 31)
    )
    assert len(session.queries) == 2  # summary + time-of-day series
    for query in session.queries:
        assert "t.DATE_ONLY = '2026-10-30'::DATE" in query
        assert 'CURRENT_TIMESTAMP' not in query
    assert rows[0]['target_date'] == date(2026, 10, 30)


# --------------------------------------------------------------------------- report building

def _patch_pipeline(monkeypatch, *, events, new_rows=(), enduring_rows=(), anomaly_rows=(), reported_rows=()):
    calls = {'fetched': [], 'pdf': None}

    def fake_fetch(filters, limit=10, *, kind='new', report_date=None):
        calls['fetched'].append((kind, report_date))
        return list({'new': new_rows, 'enduring': enduring_rows, 'enduring_reported': reported_rows}[kind])

    def fake_anomalies(filters, report_date=None):
        calls['fetched'].append(('anomalies', report_date))
        return list(anomaly_rows), 4.0

    def fake_pdf(filters, rows, **kwargs):
        calls['pdf'] = kwargs
        return b'%PDF-fake'

    monkeypatch.setattr(report_service, 'fetch_monitoring_rows', fake_fetch)
    monkeypatch.setattr(report_service, 'fetch_monitoring_anomaly_rows', fake_anomalies)
    monkeypatch.setattr(report_service, 'enrich_monitoring_rows', lambda rows, **kw: [dict(r) for r in rows])
    monkeypatch.setattr(report_service, 'build_monitoring_pdf', fake_pdf)
    monkeypatch.setattr(report_service.joke_service, 'prepare_joke', lambda report_date: None)
    monkeypatch.setattr(
        report_service.algorithm_changes, 'fetch_algorithm_changes',
        lambda *a, **kw: algorithm_changes.filter_overlapping(_events(*events), *a),
    )
    return calls


def test_build_report_leaves_out_section_inside_event(monkeypatch):
    calls = _patch_pipeline(
        monkeypatch,
        events=[OCT_EVENT],
        new_rows=[{'xd': 1, 'timestamp': datetime(2026, 10, 22, 8)}],
        enduring_rows=[{'xd': 2, 'timestamp': datetime(2026, 10, 9, 8), 'kind': 'enduring'}],
        reported_rows=[{'xd': 4, 'timestamp': datetime(2026, 10, 9, 9)}],
        anomaly_rows=[{'xd': 3, 'severity_score': 10.0}],
    )
    report = report_service.build_report({}, report_date=date(2026, 10, 31))

    # The new-changepoint section (day 10/22) is never queried; the others use the report date
    assert ('new', date(2026, 10, 31)) not in calls['fetched']
    assert ('enduring', date(2026, 10, 31)) in calls['fetched']
    assert ('enduring_reported', date(2026, 10, 31)) in calls['fetched']
    assert ('anomalies', date(2026, 10, 31)) in calls['fetched']
    assert report['no_data'] is False
    assert report['excluded_sections'] == ['new']
    assert report['changepoints'] == 0
    assert report['enduring_changepoints'] == 1
    assert report['enduring_reported'] == 1
    assert report['anomalies'] == 1

    html = report['html']
    assert html.index('INRIX algorithm change') < html.index('Your report')
    assert 'New changepoints from Oct 21&ndash;22 omitted.' in html
    assert '2 enduring (1 already reported), 1 anomaly; new changepoints omitted (INRIX algorithm change)' in html

    # PDF gets ASCII notes, the empty-state text for the left-out section, and the reported table rows
    assert calls['pdf']['algorithm_notes'][0].startswith('INRIX algorithm change on Oct 22, 2026')
    assert calls['pdf']['enduring_reported_rows'] == [{'xd': 4, 'timestamp': datetime(2026, 10, 9, 9)}]
    assert 'Oct 21-22' in calls['pdf']['algorithm_notes'][0]
    assert 'algorithm change' in calls['pdf']['excluded_text']['new']
    assert 'enduring' not in calls['pdf']['excluded_text']


def test_report_empty_only_because_of_event_is_still_sent(monkeypatch):
    _patch_pipeline(monkeypatch, events=[OCT_EVENT])
    sent = {}
    monkeypatch.setattr(report_service.email_service, 'send_email',
                        lambda email, subject, html, attachments=None: sent.update(html=html, subject=subject))
    monkeypatch.setattr(report_service, 'DEBUG_SAVE_REPORT_PDF', False)

    result = report_service.generate_and_send_report('someone@example.gov', {}, report_date=date(2026, 10, 31))
    assert result['sent'] is True
    assert result['excluded_sections'] == ['new']
    assert sent['subject'].endswith('2026-10-31')
    assert 'omitted' in sent['html']


def test_report_without_rows_or_events_is_no_data(monkeypatch):
    _patch_pipeline(monkeypatch, events=[OCT_EVENT])
    report = report_service.build_report({}, report_date=date(2026, 11, 24))
    assert report['no_data'] is True
    assert report['excluded_sections'] == []
    assert 'pdf_bytes' not in report


def test_report_with_only_reported_enduring_rows_is_sent(monkeypatch):
    _patch_pipeline(monkeypatch, events=[], reported_rows=[{'xd': 4, 'timestamp': datetime(2026, 11, 2, 9)}])
    report = report_service.build_report({}, report_date=date(2026, 11, 24))
    assert report['no_data'] is False
    assert '0 new changepoints, 1 enduring (1 already reported), 0 anomalies' in report['html']


@pytest.mark.parametrize('kwargs,expected', [
    (dict(new_count=1, enduring_count=1, enduring_reported_count=1, anomaly_count=3),
     '1 new changepoint, 2 enduring (1 already reported), 3 anomalies'),
    (dict(new_count=0, enduring_count=2, enduring_reported_count=0, anomaly_count=1),
     '0 new changepoints, 2 enduring, 1 anomaly'),
    (dict(new_count=0, enduring_count=0, enduring_reported_count=0, anomaly_count=0,
          excluded_sections=['anomalies', 'new', 'enduring']),
     'Anomalies, new changepoints, and enduring changepoints omitted (INRIX algorithm change)'),
])
def test_report_counts_text(kwargs, expected):
    assert report_service.report_counts_text(**kwargs) == expected


def test_report_date_from_filters_is_respected(monkeypatch):
    calls = _patch_pipeline(monkeypatch, events=[], anomaly_rows=[{'xd': 3, 'severity_score': 10.0}])
    report = report_service.build_report({'report_date': '2026-10-15'})
    assert report['report_date'] == date(2026, 10, 15)
    assert {item[1] for item in calls['fetched']} == {date(2026, 10, 15)}


def test_build_monitoring_pdf_with_algorithm_note():
    pytest.importorskip('fpdf')
    pytest.importorskip('matplotlib')
    impact = algorithm_changes.report_impact(date(2026, 10, 31), _events(OCT_EVENT), dash='-')
    pdf_bytes = report_service.build_monitoring_pdf(
        {}, [], enduring_rows=[], report_date=date(2026, 10, 31),
        algorithm_notes=impact['notes'], excluded_text=impact['excluded_text'],
    )
    assert pdf_bytes.startswith(b'%PDF')

    reported = [{
        'xd': 1236908576 + i, 'timestamp': datetime(2026, 10, 9, 8), 'roadname': 'A Very Long Road Name Boulevard Extension',
        'bearing': 'NB', 'associated_signals': '01001, 01005, 01006, 01007', 'before_tt': 61.2, 'after_tt': 70.4,
        'enduring_tt': 69.9, 'pct_change': 0.15 - i * 0.05, 'severity_score': 100 - i,
    } for i in range(10)]
    with_table = report_service.build_monitoring_pdf(
        {}, [], enduring_rows=[], enduring_reported_rows=reported, report_date=date(2026, 10, 31),
    )
    assert with_table.startswith(b'%PDF')


# --------------------------------------------------------------------------- routes

def test_algorithm_changes_route(client, monkeypatch):
    monkeypatch.setattr(
        algorithm_changes, 'fetch_algorithm_changes',
        lambda start=None, end=None, **kw: algorithm_changes.filter_overlapping(_events(SEP_EVENT, OCT_EVENT), start, end),
    )
    response = client.get('/api/algorithm-changes', query_string={'start_date': '2026-10-01', 'end_date': '2026-10-31'})
    assert response.status_code == 200
    payload = response.get_json()
    assert [e['event_date'] for e in payload['events']] == ['2026-10-22']
    assert payload['events'][0]['segments'] == 1099

    response = client.get('/api/algorithm-changes', query_string={'start_date': 'not-a-date'})
    assert response.status_code == 400


def test_algorithm_changes_route_reports_failure(client, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError('no access')

    monkeypatch.setattr(algorithm_changes, 'fetch_algorithm_changes', broken)
    response = client.get('/api/algorithm-changes')
    assert response.status_code == 502
    assert response.get_json()['events'] == []


def test_report_impact_route(client, monkeypatch):
    monkeypatch.setattr(
        algorithm_changes, 'fetch_algorithm_changes',
        lambda start=None, end=None, **kw: algorithm_changes.filter_overlapping(_events(OCT_EVENT), start, end),
    )
    response = client.get('/api/algorithm-changes/report-impact', query_string={'report_date': '2026-10-31'})
    payload = response.get_json()
    assert payload['excluded_sections'] == ['new']
    assert payload['section_days']['new'] == '2026-10-22'
    assert payload['notes'][0].endswith('New changepoints from Oct 21–22 omitted.')


def test_changepoints_route_enduring_unreported_type(client, monkeypatch):
    captured = {}

    def fake_execute(query):
        captured['query'] = query
        return b'arrow-bytes', 200, {'Content-Type': 'application/octet-stream'}

    monkeypatch.setattr(api_changepoints, 'handle_auth_error_retry', lambda fn: fn())
    monkeypatch.setattr(api_changepoints, '_execute_arrow_query', fake_execute)
    client.get('/api/changepoints-table', query_string={
        'start_date': '2026-11-02', 'end_date': '2026-11-02', 'changepoint_type': 'enduring_unreported',
    })
    query = captured['query']
    assert 't.IS_ENDURING = TRUE AND t.IS_CHANGEPOINT = FALSE' in query
    assert "t.TIMESTAMP >= '2026-11-02' AND t.TIMESTAMP < DATEADD(day, 1, '2026-11-02'::DATE)" in query
    assert 'ORDER BY SCORE DESC, ABS(t.PCT_CHANGE) DESC, t.TIMESTAMP DESC' in query


def test_changepoints_route_enduring_reported_type(client, monkeypatch):
    captured = {}

    def fake_execute(query):
        captured['query'] = query
        return b'arrow-bytes', 200, {'Content-Type': 'application/octet-stream'}

    monkeypatch.setattr(api_changepoints, 'handle_auth_error_retry', lambda fn: fn())
    monkeypatch.setattr(api_changepoints, '_execute_arrow_query', fake_execute)
    client.get('/api/changepoints-table', query_string={
        'start_date': '2026-11-02', 'end_date': '2026-11-02', 'changepoint_type': 'enduring_reported',
    })
    query = captured['query']
    assert 't.IS_ENDURING = TRUE AND COALESCE(t.IS_CHANGEPOINT, TRUE)' in query
    # Travel times for the compact "already reported" table
    for column in ('t.BEFORE_TT', 't.AFTER_TT', 't.ENDURING_TT'):
        assert column in query

"""
INRIX algorithm changes (system-wide travel time shifts), detected from CHANGEPOINTS.

Rule: a day whose busiest one-hour window has changepoints on 80+ segments is an
algorithm change; adjacent days (+/- 1) with 25+ in their busiest hour join its span.
Known INRIX changes peak at 113-284 segments per hour in CHANGEPOINTS; every other day
peaks at 53 or fewer.

Also holds the report helpers: which report sections fall on an event day and the
note text shown at the top of the PDF, the email and the Monitoring page.
"""

from __future__ import annotations

import math
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import TIMEZONE
from database import get_snowflake_session
from utils.error_handler import handle_auth_error_retry

CACHE_TTL_SECONDS = 3600

PEAK_SEGMENTS_THRESHOLD = 80      # segments with a changepoint within one hour
NEIGHBOR_SEGMENTS_THRESHOLD = 25  # adjacent days at or above this join the event span

DETECTION_SQL = f"""
WITH src AS (SELECT XD, TIMESTAMP, PCT_CHANGE FROM CHANGEPOINTS WHERE COALESCE(IS_CHANGEPOINT, TRUE)),
slots AS (SELECT TIMESTAMP, COUNT(*) N FROM src GROUP BY 1),
rolling AS (SELECT TIMESTAMP, SUM(N) OVER (ORDER BY TIMESTAMP RANGE BETWEEN INTERVAL '59 MINUTES' PRECEDING AND CURRENT ROW) N FROM slots),
days AS (SELECT TO_DATE(TIMESTAMP) D, MAX(N) PEAK, MAX_BY(TIMESTAMP, N) PEAK_TS FROM rolling GROUP BY 1),
spans AS (SELECT e.PEAK_TS, e.PEAK, MIN(d.D) START_DATE, MAX(d.D) END_DATE FROM days e
          JOIN days d ON d.D BETWEEN e.D - 1 AND e.D + 1 AND (d.D = e.D OR d.PEAK >= {NEIGHBOR_SEGMENTS_THRESHOLD})
          WHERE e.PEAK >= {PEAK_SEGMENTS_THRESHOLD} GROUP BY 1, 2)
SELECT TO_DATE(s.PEAK_TS) EVENT_DATE, s.PEAK_TS PEAK_TIMESTAMP, s.START_DATE, s.END_DATE, s.PEAK PEAK_HOUR_SEGMENTS,
    COUNT(DISTINCT c.XD) SEGMENTS, ROUND(AVG(IFF(c.PCT_CHANGE > 0, 1, 0)), 3) SHARE_SLOWER
FROM spans s JOIN src c ON TO_DATE(c.TIMESTAMP) BETWEEN s.START_DATE AND s.END_DATE
GROUP BY 1, 2, 3, 4, 5 ORDER BY 1
"""

# Report sections and how many days before the report date each one covers.
REPORT_SECTION_LAG_DAYS: Dict[str, int] = {
    "anomalies": 1,
    "new": 9,
    "enduring": 22,
}
REPORT_SECTION_LABELS: Dict[str, str] = {
    "anomalies": "anomalies",
    "new": "new changepoints",
    "enduring": "enduring changepoints",
}
REPORT_SECTION_ORDER: Tuple[str, ...] = ("anomalies", "new", "enduring")

_cache_lock = threading.Lock()
_cache: Dict[str, Any] = {"events": None, "loaded_at": 0.0}


def clear_cache() -> None:
    with _cache_lock:
        _cache.update(events=None, loaded_at=0.0)


def _coerce_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo is None else _to_local_naive(value)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    try:
        return datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _local_zone() -> Optional[ZoneInfo]:
    try:
        return ZoneInfo(TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _to_local_naive(value: datetime) -> datetime:
    zone = _local_zone() or ZoneInfo("UTC")
    return value.astimezone(zone).replace(tzinfo=None)


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> Optional[float]:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _normalize_row(row: Any) -> Optional[Dict[str, Any]]:
    data = row.as_dict() if hasattr(row, "as_dict") else dict(row)
    data = {str(key).upper(): value for key, value in data.items()}
    start = _coerce_date(data.get("START_DATE"))
    end = _coerce_date(data.get("END_DATE"))
    event_date = _coerce_date(data.get("EVENT_DATE"))
    if start is None or end is None:
        return None
    return {
        "event_date": event_date or end,
        "peak_timestamp": _coerce_datetime(data.get("PEAK_TIMESTAMP")),
        "start_date": start,
        "end_date": end,
        "peak_hour_segments": _int_or_none(data.get("PEAK_HOUR_SEGMENTS")),
        "segments": _int_or_none(data.get("SEGMENTS")),
        "share_slower": _float_or_none(data.get("SHARE_SLOWER")),
    }


def _run_query(sql: str) -> List[Dict[str, Any]]:
    def execute() -> List[Dict[str, Any]]:
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise RuntimeError("Unable to establish database connection for algorithm changes")
        rows = [_normalize_row(row) for row in session.sql(sql).collect()]
        return [row for row in rows if row is not None]

    return handle_auth_error_retry(execute)


def _load_all_events() -> List[Dict[str, Any]]:
    """Detect algorithm changes from CHANGEPOINTS."""
    events = _run_query(DETECTION_SQL)
    events.sort(key=lambda item: (item["start_date"], item["end_date"]))
    print(f"[INFO] Algorithm changes: detected {len(events)} event(s) from CHANGEPOINTS")
    return events


def fetch_algorithm_changes(
    start_date: Any = None,
    end_date: Any = None,
    *,
    use_cache: bool = True,
) -> List[Dict[str, Any]]:
    """
    Return detected INRIX algorithm changes whose [START_DATE, END_DATE] span overlaps
    the given (inclusive) date range. Either bound may be omitted.

    Results are cached in-process for an hour (events change at most daily).
    Raises if the CHANGEPOINTS query fails.
    """
    now = time.monotonic()
    with _cache_lock:
        cached = _cache["events"]
        fresh = cached is not None and (now - _cache["loaded_at"]) < CACHE_TTL_SECONDS
    if use_cache and fresh:
        events = cached
    else:
        events = _load_all_events()
        with _cache_lock:
            _cache.update(events=events, loaded_at=time.monotonic())

    return filter_overlapping(events, start_date, end_date)


def filter_overlapping(events: Sequence[Dict[str, Any]], start_date: Any = None, end_date: Any = None) -> List[Dict[str, Any]]:
    """Keep events whose span overlaps the inclusive range [start_date, end_date]."""
    start = _coerce_date(start_date)
    end = _coerce_date(end_date)
    if start and end and start > end:
        start, end = end, start
    result = []
    for event in events:
        if start and event["end_date"] < start:
            continue
        if end and event["start_date"] > end:
            continue
        result.append(dict(event))
    return result


def event_covering(day: Optional[date], events: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if day is None:
        return None
    for event in events:
        if event["start_date"] <= day <= event["end_date"]:
            return event
    return None


# --------------------------------------------------------------------------- formatting

def _month_day(value: date) -> str:
    return f"{value.strftime('%b')} {value.day}"


def format_span(event: Dict[str, Any], dash: str = "–", *, with_year: bool = True) -> str:
    """'Oct 22, 2026', 'Oct 21-22, 2026' or 'Dec 31, 2025-Jan 1, 2026' (dash configurable)."""
    start, end = event["start_date"], event["end_date"]
    year = f", {end.year}" if with_year else ""
    if start == end:
        return f"{_month_day(end)}{year}"
    if start.year != end.year:
        return f"{_month_day(start)}, {start.year}{dash}{_month_day(end)}, {end.year}"
    if start.month == end.month:
        return f"{_month_day(start)}{dash}{end.day}{year}"
    return f"{_month_day(start)}{dash}{_month_day(end)}{year}"


def format_clock(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    return f"{hour}:{value.minute:02d} {suffix}"


def approx_count(value: Optional[int]) -> str:
    """Round a segment count for prose: 1099 -> '1,100', 483 -> '480'."""
    if value is None:
        return "many"
    if value >= 1000:
        rounded = int(round(value / 100.0)) * 100
    elif value >= 100:
        rounded = int(round(value / 10.0)) * 10
    else:
        rounded = int(value)
    return f"{rounded:,}"


def _join_labels(labels: Sequence[str]) -> str:
    if len(labels) <= 1:
        return "".join(labels)
    if len(labels) == 2:
        return f"{labels[0]} and {labels[1]}"
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def _event_sentence(event: Dict[str, Any]) -> str:
    """'INRIX algorithm change on Oct 22, 2026 (~1,100 segments shifted at 2:30 PM).'"""
    peak_day = event.get("event_date") or event["end_date"]
    peak = format_clock(event.get("peak_timestamp"))
    detail = f"~{approx_count(event.get('segments'))} segments shifted"
    if peak:
        detail += f" at {peak}"
    return f"INRIX algorithm change on {_month_day(peak_day)}, {peak_day.year} ({detail})."


# --------------------------------------------------------------------------- report impact

def report_section_days(report_date: date) -> Dict[str, date]:
    """Day covered by each report section for report date R (anomalies R-1, new R-9, enduring R-22)."""
    return {section: report_date - timedelta(days=lag) for section, lag in REPORT_SECTION_LAG_DAYS.items()}


def report_impact(
    report_date: date,
    events: Optional[Sequence[Dict[str, Any]]] = None,
    *,
    dash: str = "–",
) -> Dict[str, Any]:
    """
    Work out which report sections fall on an algorithm-change day.

    Returns:
        excluded: {section: event} for sections to leave out
        notes: one short note per event that empties a section (shown at the top)
        excluded_text: {section: short empty-state text}
        events: events that overlap any section day
        error: message when events could not be loaded (report proceeds without them)
    """
    section_days = report_section_days(report_date)
    error: Optional[str] = None
    if events is None:
        try:
            events = fetch_algorithm_changes(min(section_days.values()), max(section_days.values()))
        except Exception as exc:  # pragma: no cover - logged and ignored
            print(f"[ERROR] Algorithm changes unavailable; report sent without event filtering: {exc}")
            events = []
            error = str(exc)

    excluded: Dict[str, Dict[str, Any]] = {}
    for section in REPORT_SECTION_ORDER:
        event = event_covering(section_days[section], events)
        if event is not None:
            excluded[section] = event

    notes: List[str] = []
    excluded_text: Dict[str, str] = {}
    seen: List[Dict[str, Any]] = []
    for section in REPORT_SECTION_ORDER:
        event = excluded.get(section)
        if event is None or any(event is item for item in seen):
            continue
        seen.append(event)
        sections = [s for s in REPORT_SECTION_ORDER if excluded.get(s) is event]
        labels = [REPORT_SECTION_LABELS[s] for s in sections]
        label_text = _join_labels(labels)
        label_text = label_text[:1].upper() + label_text[1:]
        span = format_span(event, dash, with_year=False)
        notes.append(f"{_event_sentence(event)} {label_text} from {span} omitted.")
        for s in sections:
            excluded_text[s] = f"Omitted: INRIX algorithm change on {format_span(event, dash)}."

    return {
        "report_date": report_date,
        "section_days": section_days,
        "excluded": excluded,
        "excluded_text": excluded_text,
        "notes": notes,
        "events": [event for event in events if any(
            event["start_date"] <= day <= event["end_date"] for day in section_days.values()
        )],
        "error": error,
    }


def serialize_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """JSON-friendly event; peak_timestamp carries the local UTC offset so browsers place it correctly."""
    peak = event.get("peak_timestamp")
    peak_iso = None
    peak_local = None
    if isinstance(peak, datetime):
        peak_local = peak.strftime("%Y-%m-%dT%H:%M:%S")
        zone = _local_zone()
        peak_iso = (peak.replace(tzinfo=zone) if zone else peak).isoformat()
    return {
        "event_date": event["event_date"].isoformat() if event.get("event_date") else None,
        "peak_timestamp": peak_iso,
        "peak_local": peak_local,
        "start_date": event["start_date"].isoformat(),
        "end_date": event["end_date"].isoformat(),
        "peak_hour_segments": event.get("peak_hour_segments"),
        "segments": event.get("segments"),
        "share_slower": event.get("share_slower"),
    }

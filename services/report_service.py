"""
Monitoring report data collection, PDF generation, and email delivery.
"""

from __future__ import annotations

import io
import math
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from fpdf import FPDF
except ImportError:  # pragma: no cover - optional dependency during testing
    FPDF = None  # type: ignore

try:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import dates as mdates
    from matplotlib import pyplot as plt
except ImportError:  # pragma: no cover - optional dependency during testing
    matplotlib = None  # type: ignore
    mdates = None  # type: ignore
    plt = None  # type: ignore

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import (
    ANOMALY_MONITORING_THRESHOLD,
    CHANGEPOINT_SEVERITY_THRESHOLD,
    BASE_DIR,
    DAILY_REPORT_SEND_HOUR,
    DEBUG_SAVE_REPORT_PDF,
    EMAIL_SENDER_NAME,
    TIMEZONE,
)
from database import get_snowflake_session
from services import email_service, joke_service, subscription_store
from utils.query_utils import normalize_date
from utils.error_handler import handle_auth_error_retry


def _percent(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"{float(value) * 100:.1f}%"


def _seconds(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"{float(value):.1f} s"


BEFORE_SERIES_RGB: Tuple[int, int, int] = (25, 118, 210)
AFTER_SERIES_RGB: Tuple[int, int, int] = (245, 124, 0)
BEFORE_SERIES_HEX = "#1976D2"
AFTER_SERIES_HEX = "#F57C00"
ANOMALY_ACTUAL_HEX = "#1976D2"
ANOMALY_FORECAST_HEX = "#1F1F24"
ANOMALY_FORECAST_LINESTYLE = (2, 4)
JOKE_IMAGE_MAX_WIDTH_PT = 6 * 72  # match ATSPM_Report scaling (approx 6 inches)
JOKE_IMAGE_MAX_HEIGHT_PT = 4 * 72  # approx 4 inches
COMPOSITE_FIG_WIDTH_IN = 6.8
COMPOSITE_FIG_HEIGHT_IN = 3.3
COMPOSITE_FIG_RATIO = COMPOSITE_FIG_HEIGHT_IN / COMPOSITE_FIG_WIDTH_IN
ANOMALY_FIG_HEIGHT_IN = 2.8

# SQL expression that mirrors the severity score used to rank changepoints
_CHANGEPOINT_SEVERITY_SQL = (
    "COALESCE(ABS(t.PCT_CHANGE * t.AVG_DIFF) * 100, 0)"
)


def _trend_callout(pct_change: Any) -> Tuple[str, Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]:
    """Return styling hints for the percent-change callout."""
    value = _safe_float(pct_change)
    if math.isnan(value):
        return (
            "Travel time change unavailable",
            (248, 249, 253),
            (226, 231, 240),
            (87, 96, 106),
        )

    change_pct = value * 100
    abs_change = abs(change_pct)

    if abs_change < 0.5:
        return (
            "Travel time is steady (<0.5% change)",
            (244, 247, 252),
            (222, 231, 246),
            (66, 82, 110),
        )

    if change_pct > 0:
        return (
            f"{change_pct:.1f}% slower than the prior week",
            (255, 244, 229),
            (255, 224, 178),
            (191, 87, 0),
        )

    return (
        f"{abs_change:.1f}% faster than the prior week",
        (232, 245, 233),
        (200, 230, 201),
        (46, 125, 50),
    )


def _write_full_width(pdf, text: str, height: float) -> None:
    """Helper to render multi-line text using the full printable width."""
    pdf.set_x(pdf.l_margin)
    usable_width = pdf.w - pdf.l_margin - pdf.r_margin
    if usable_width <= 0:
        usable_width = pdf.w
    pdf.multi_cell(usable_width, height, text)


def _write_paragraph_with_links(
    pdf,
    segments: Sequence[Tuple[str, Optional[str]]],
    *,
    line_height: float = 14,
    base_color: Tuple[int, int, int] = (62, 72, 85),
    link_color: Tuple[int, int, int] = (25, 118, 210),
) -> None:
    """Render a paragraph that mixes plain text and clickable links."""
    pdf.set_text_color(*base_color)
    pdf.set_x(pdf.l_margin)
    for text, link in segments:
        if not text:
            continue
        if link:
            pdf.set_text_color(*link_color)
            pdf.write(line_height, text, link)
            pdf.set_text_color(*base_color)
        else:
            pdf.write(line_height, text)
    pdf.ln(line_height)


def _clean_text(value: Any, fallback: str = "") -> str:
    """Translate arbitrary text to ASCII-safe content for documents."""
    if value is None:
        return fallback
    text = str(value)
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    return ascii_text or fallback


def _resolve_report_date(filters: Dict[str, Any]) -> date:
    """Determine the report date for joke selection."""
    raw_end = filters.get("end_date")
    if raw_end:
        raw_str = str(raw_end)
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(raw_str, fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(raw_str).date()
        except ValueError:
            pass

    try:
        zone = ZoneInfo(TIMEZONE)
        return datetime.now(zone).date()
    except (ZoneInfoNotFoundError, ValueError):
        return datetime.utcnow().date()

def _ordinal_suffix(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"

def _format_report_date(value: Optional[date]) -> str:
    if not value:
        return "the selected date range"
    month_name = value.strftime("%B")
    return f"{month_name} {_ordinal_suffix(value.day)}, {value.year}"


def _coerce_date(value: Any) -> Optional[date]:
    """Best-effort conversion of assorted values into a date."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            try:
                return datetime.fromisoformat(candidate).date()
            except ValueError:
                return None
    return None


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _local_zone() -> Optional[ZoneInfo]:
    try:
        return ZoneInfo(TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _local_today() -> date:
    """Return today's date in the configured timezone."""
    zone = _local_zone()
    if zone is None:
        return datetime.utcnow().date()
    return datetime.now(zone).date()


def _default_monitoring_window(reference: Optional[date] = None) -> Tuple[str, str]:
    """
    Mirror the frontend monitoring window selection.

    The current UI looks nine days back for the start date and one day forward from
    that for the end date (effectively the same weekday from the prior week).
    """
    anchor = reference or _local_today()
    start_date = anchor - timedelta(days=9)
    end_date = start_date + timedelta(days=1)
    return start_date.isoformat(), end_date.isoformat()


def _combine_date_minutes(target_date: date, minutes: int) -> datetime:
    """Create a timestamp on the given date at the provided minute-of-day."""
    minutes = int(minutes)
    return datetime.combine(target_date, datetime.min.time()) + timedelta(minutes=minutes)


def _to_local_naive(timestamp: datetime) -> datetime:
    """Return a naive datetime that represents local wall-clock time"""
    if timestamp.tzinfo is None:
        return timestamp
    zone = _local_zone()
    if zone is not None:
        return timestamp.astimezone(zone).replace(tzinfo=None)
    return timestamp.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _localize_timestamp(timestamp: datetime) -> str:
    if not isinstance(timestamp, datetime):
        return str(timestamp)

    zone = _local_zone()
    if zone:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=zone)
        timestamp = timestamp.astimezone(zone)
    return timestamp.strftime("%Y-%m-%d %H:%M")


def _yesterday_date() -> date:
    """Return the local-date for yesterday."""
    zone = _local_zone()
    if zone:
        now = datetime.now(zone)
    else:
        now = datetime.utcnow()
    return (now - timedelta(days=1)).date()


def _sanitize_string_list(values: Optional[Sequence[Any]]) -> List[str]:
    """Return a SQL-safe list of quoted string values."""
    sanitized: List[str] = []
    if not values:
        return sanitized
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        sanitized.append(text.replace("'", "''"))
    return sanitized


def _sanitize_int_list(values: Optional[Sequence[Any]]) -> List[str]:
    """Return a SQL-safe list of integer literals."""
    sanitized: List[str] = []
    if not values:
        return sanitized
    for value in values:
        try:
            sanitized.append(str(int(value)))
        except (TypeError, ValueError):
            continue
    return sanitized


def _minutes_from_value(value: Any) -> Optional[int]:
    """Convert a TIME or numeric value to minutes since midnight."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    if isinstance(value, datetime):
        return value.hour * 60 + value.minute
    hour = getattr(value, "hour", None)
    minute = getattr(value, "minute", None)
    if hour is not None and minute is not None:
        try:
            return int(hour) * 60 + int(minute)
        except (TypeError, ValueError):
            return None
    text = str(value).strip()
    if ":" in text:
        parts = text.split(":")
        if len(parts) >= 2:
            try:
                return int(parts[0]) * 60 + int(parts[1][:2])
            except (TypeError, ValueError):
                return None
    try:
        return int(round(float(text)))
    except (TypeError, ValueError):
        return None


def _parse_filters(raw_filters: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize incoming filter payload."""
    selected_group_values = raw_filters.get("selected_signal_groups")
    if not selected_group_values:
        selected_group_values = raw_filters.get("selected_districts")
    if isinstance(selected_group_values, (list, tuple, set)):
        selected_groups = [
            str(item).strip() for item in selected_group_values if str(item).strip()
        ]
    elif selected_group_values:
        selected_groups = [str(selected_group_values).strip()]
    else:
        selected_groups = []

    filters = {
        "start_date": normalize_date(raw_filters.get("start_date")),
        "end_date": normalize_date(raw_filters.get("end_date")),
        "signal_ids": raw_filters.get("signal_ids") or [],
        "selected_signals": raw_filters.get("selected_signals") or raw_filters.get("signal_ids") or [],
        "selected_xds": raw_filters.get("selected_xds") or [],
        "selected_signal_groups": selected_groups,
        "maintained_by": (raw_filters.get("maintained_by") or "all"),
        "approach": raw_filters.get("approach"),
        "valid_geometry": raw_filters.get("valid_geometry"),
    }

    threshold_value = raw_filters.get("anomaly_monitoring_threshold")
    try:
        threshold_numeric = float(threshold_value)
    except (TypeError, ValueError):
        threshold_numeric = ANOMALY_MONITORING_THRESHOLD
    else:
        if not math.isfinite(threshold_numeric):
            threshold_numeric = ANOMALY_MONITORING_THRESHOLD
    filters["anomaly_monitoring_threshold"] = max(0.0, threshold_numeric)

    cp_threshold_value = raw_filters.get("changepoint_severity_threshold", CHANGEPOINT_SEVERITY_THRESHOLD)
    try:
        cp_threshold_numeric = float(cp_threshold_value)
    except (TypeError, ValueError):
        cp_threshold_numeric = CHANGEPOINT_SEVERITY_THRESHOLD
    else:
        if not math.isfinite(cp_threshold_numeric):
            cp_threshold_numeric = CHANGEPOINT_SEVERITY_THRESHOLD
    filters["changepoint_severity_threshold"] = max(0.0, cp_threshold_numeric)

    return filters


def _build_selected_filters_clause(selected_signals: Sequence[Any], selected_xds: Sequence[Any]) -> str:
    """Compose additional AND conditions for explicit signal or XD selections."""
    conditions: List[str] = []

    sanitized_signals = _sanitize_string_list(selected_signals)
    if sanitized_signals:
        ids_str = "', '".join(sanitized_signals)
        conditions.append(
            f"t.XD IN (SELECT DISTINCT XD FROM DIM_SIGNALS_XD WHERE ID IN ('{ids_str}'))"
        )

    sanitized_xds = _sanitize_int_list(selected_xds)
    if sanitized_xds:
        xds_str = ", ".join(sanitized_xds)
        conditions.append(f"t.XD IN ({xds_str})")

    return " AND ".join(conditions)


def _build_filtered_dim_components(
    signal_ids: Sequence[Any],
    maintained_by: Optional[str],
    approach: Optional[str],
    valid_geometry: Optional[str],
) -> tuple[str, str]:
    """Return JOIN/WHERE fragments for filtering DIM_SIGNALS_XD without extra joins."""
    sanitized_ids = _sanitize_string_list(signal_ids)
    join_clause = ""
    where_parts: List[str] = []

    if sanitized_ids:
        ids_str = "', '".join(sanitized_ids)
        where_parts.append(f"dim.ID IN ('{ids_str}')")

    if approach is not None and approach != '':
        approach_bool = 'TRUE' if str(approach).lower() == 'true' else 'FALSE'
        where_parts.append(f"dim.APPROACH = {approach_bool}")

    if valid_geometry is not None and valid_geometry != '' and valid_geometry != 'all':
        valid = str(valid_geometry).lower()
        if valid == 'valid':
            where_parts.append("dim.VALID_GEOMETRY = TRUE")
        elif valid == 'invalid':
            where_parts.append("dim.VALID_GEOMETRY = FALSE")

    maintained = str(maintained_by or 'all').lower()
    if maintained in {'odot', 'others'}:
        join_clause = "\n    INNER JOIN DIM_SIGNALS s ON dim.ID = s.ID"
        if maintained == 'odot':
            where_parts.append("s.ODOT_MAINTAINED = TRUE")
        else:
            where_parts.append("s.ODOT_MAINTAINED = FALSE")

    where_clause = ""
    if where_parts:
        where_clause = "\n    WHERE " + " AND ".join(where_parts)

    return join_clause, where_clause


def fetch_monitoring_rows(raw_filters: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
    """Query Snowflake for monitoring changepoints using the provided filters."""
    filters = _parse_filters(raw_filters)

    dimension_join, dimension_where_clause = _build_filtered_dim_components(
        filters["signal_ids"],
        filters["maintained_by"],
        filters["approach"],
        filters["valid_geometry"],
    )

    where_parts = [
        "t.TIMESTAMP >= DATEADD(day, -9, DATE_TRUNC('day', CURRENT_TIMESTAMP()))",
    ]

    severity_threshold = _safe_float(filters.get("changepoint_severity_threshold"))
    if not math.isfinite(severity_threshold):
        severity_threshold = CHANGEPOINT_SEVERITY_THRESHOLD
    severity_threshold = max(0.0, severity_threshold)
    severity_clause = f"{_CHANGEPOINT_SEVERITY_SQL} >= {severity_threshold:.6f}"
    where_parts.append(severity_clause)

    sanitized_selected_signals = _sanitize_string_list(filters.get("selected_signals"))
    if sanitized_selected_signals:
        ids_str = "', '".join(sanitized_selected_signals)
        where_parts.append(
            f"t.XD IN (SELECT DISTINCT XD FROM DIM_SIGNALS_XD WHERE ID IN ('{ids_str}'))"
        )

    sanitized_selected_xds = _sanitize_int_list(filters.get("selected_xds"))
    if sanitized_selected_xds:
        xds_str = ", ".join(sanitized_selected_xds)
        where_parts.append(f"t.XD IN ({xds_str})")

    where_clause = " AND ".join(where_parts)

    query = f"""
    SELECT
        t.XD AS XD,
        t.TIMESTAMP,
        t.PCT_CHANGE,
        t.AVG_DIFF,
        t.AVG_BEFORE,
        t.AVG_AFTER,
        {_CHANGEPOINT_SEVERITY_SQL} AS SCORE,
        xd.ROADNAME,
        xd.BEARING,
        LISTAGG(DISTINCT xd.ID, ', ') WITHIN GROUP (ORDER BY xd.ID) AS ASSOCIATED_SIGNALS
    FROM CHANGEPOINTS t
    INNER JOIN (
        SELECT DISTINCT
            dim.XD,
            dim.ID,
            dim.ROADNAME,
            dim.BEARING
        FROM DIM_SIGNALS_XD dim{dimension_join}{dimension_where_clause}
    ) xd ON t.XD = xd.XD
    WHERE {where_clause}
    GROUP BY ALL
    ORDER BY SCORE DESC, ABS(t.PCT_CHANGE) DESC, t.TIMESTAMP DESC
    LIMIT {limit}
    """

    def execute_query() -> List[Dict[str, Any]]:
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise RuntimeError("Unable to establish database connection for monitoring report")

        result_rows = session.sql(query).collect()
        rows: List[Dict[str, Any]] = []

        for row in result_rows:
            timestamp_value = row["TIMESTAMP"]
            if isinstance(timestamp_value, datetime):
                timestamp_value = _to_local_naive(timestamp_value)

            try:
                severity_value = _safe_float(row["SCORE"])
            except KeyError:
                severity_value = float("nan")
            record = {
                "xd": row["XD"],
                "timestamp": timestamp_value,
                "pct_change": row["PCT_CHANGE"],
                "avg_diff": row["AVG_DIFF"],
                "avg_before": row["AVG_BEFORE"],
                "avg_after": row["AVG_AFTER"],
                "score": severity_value,
                "severity_score": severity_value,
                "roadname": row["ROADNAME"],
                "bearing": row["BEARING"],
                "associated_signals": row["ASSOCIATED_SIGNALS"],
            }
            rows.append(record)

        return rows

    return handle_auth_error_retry(execute_query)


def fetch_monitoring_anomaly_rows(raw_filters: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], float]:
    """Query Snowflake for yesterday's anomalies using monitoring filters."""
    filters = _parse_filters(raw_filters)
    threshold_value = filters.get("anomaly_monitoring_threshold", ANOMALY_MONITORING_THRESHOLD)
    try:
        threshold = float(threshold_value)
    except (TypeError, ValueError):
        threshold = ANOMALY_MONITORING_THRESHOLD
    if not math.isfinite(threshold):
        threshold = ANOMALY_MONITORING_THRESHOLD
    threshold = max(0.0, threshold)
    threshold_sql = f"{threshold:.6f}"

    dimension_join, dimension_where_clause = _build_filtered_dim_components(
        filters["signal_ids"],
        filters["maintained_by"],
        filters["approach"],
        filters["valid_geometry"],
    )

    selected_clause = _build_selected_filters_clause(
        filters["selected_signals"], filters["selected_xds"]
    )
    selected_clause_sql = f" AND {selected_clause}" if selected_clause else ""

    query = f"""
    WITH filtered_dim AS (
        SELECT DISTINCT
            dim.XD,
            dim.ID,
            dim.ROADNAME,
            dim.BEARING
        FROM DIM_SIGNALS_XD dim{dimension_join}{dimension_where_clause}
    ),
    signal_ids AS (
        SELECT
            XD,
            LISTAGG(DISTINCT ID, ', ') WITHIN GROUP (ORDER BY ID) AS ASSOCIATED_SIGNALS
        FROM filtered_dim
        GROUP BY XD
    ),
    distinct_dim AS (
        SELECT DISTINCT
            XD,
            ROADNAME,
            BEARING
        FROM filtered_dim
    ),
    aggregated AS (
        SELECT
            t.XD,
            d.ROADNAME,
            d.BEARING,
            s.ASSOCIATED_SIGNALS,
            COUNT(*) AS TOTAL_SAMPLES,
            COUNT(CASE WHEN t.ORIGINATED_ANOMALY = TRUE THEN 1 END) AS ANOMALY_SAMPLES,
            COALESCE(
                SUM(
                    CASE
                        WHEN t.ORIGINATED_ANOMALY = TRUE THEN (t.TRAVEL_TIME_SECONDS - t.PREDICTION)
                        ELSE 0
                    END
                ),
                0
            ) AS TOTAL_EXCESS_SECONDS
        FROM TRAVEL_TIME_ANALYTICS t
        INNER JOIN distinct_dim d ON t.XD = d.XD
        LEFT JOIN signal_ids s ON t.XD = s.XD
        WHERE t.DATE_ONLY >= DATEADD(day, -1, DATE_TRUNC('day', CURRENT_TIMESTAMP())){selected_clause_sql}
        GROUP BY ALL
    ),
    scored AS (
        SELECT
            a.*,
            POWER(
                a.ANOMALY_SAMPLES::FLOAT / NULLIF(a.TOTAL_SAMPLES::FLOAT, 0),
                2
            ) * (a.TOTAL_EXCESS_SECONDS / 60.0) * 100 AS SEVERITY_SCORE
        FROM aggregated a
    )
    SELECT
        XD,
        ROADNAME,
        BEARING,
        ASSOCIATED_SIGNALS,
        TOTAL_SAMPLES,
        ANOMALY_SAMPLES,
        TOTAL_EXCESS_SECONDS,
        SEVERITY_SCORE
    FROM scored
    WHERE SEVERITY_SCORE > {threshold_sql}
    ORDER BY SEVERITY_SCORE DESC, XD
    """

    def execute_query() -> Tuple[List[Dict[str, Any]], float]:
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise RuntimeError("Unable to establish database connection for anomaly monitoring")

        records = session.sql(query).collect()
        if not records:
            return [], threshold

        yesterday = _yesterday_date()
        rows: List[Dict[str, Any]] = []
        xds: List[int] = []
        for record in records:
            data = record.as_dict() if hasattr(record, "as_dict") else dict(record)
            xd_value = data.get("XD")
            try:
                xd = int(xd_value)
            except (TypeError, ValueError):
                continue

            total_samples_value = data.get("TOTAL_SAMPLES")
            try:
                total_samples = int(total_samples_value)
            except (TypeError, ValueError):
                total_samples = 0

            anomaly_samples_value = data.get("ANOMALY_SAMPLES")
            try:
                anomaly_samples = int(anomaly_samples_value)
            except (TypeError, ValueError):
                anomaly_samples = 0

            excess_seconds = _safe_float(data.get("TOTAL_EXCESS_SECONDS"))
            excess_minutes = (
                excess_seconds / 60.0 if math.isfinite(excess_seconds) else math.nan
            )
            severity_value = _safe_float(data.get("SEVERITY_SCORE"))
            if math.isnan(severity_value):
                severity_value = 0.0

            row = {
                "xd": xd,
                "roadname": data.get("ROADNAME"),
                "bearing": data.get("BEARING"),
                "associated_signals": data.get("ASSOCIATED_SIGNALS"),
                "target_date": yesterday,
                "time_of_day_series": [],
                "total_sample_count": total_samples,
                "anomaly_sample_count": anomaly_samples,
                "excess_travel_time_minutes": excess_minutes,
                "severity_score": severity_value,
            }
            rows.append(row)
            xds.append(xd)

        if not xds:
            return rows, threshold

        xd_literals = ", ".join(str(xd) for xd in sorted(set(xds)))
        time_query = f"""
        WITH params AS (
            SELECT
                DATEADD(day, -1, DATE_TRUNC('day', CURRENT_TIMESTAMP())) AS TARGET_DATE
        )
        SELECT
            t.XD,
            t.TIME_15MIN,
            AVG(t.TRAVEL_TIME_SECONDS) AS AVG_ACTUAL,
            AVG(t.PREDICTION) AS AVG_PREDICTION
        FROM TRAVEL_TIME_ANALYTICS t
        JOIN params p ON t.DATE_ONLY = CAST(p.TARGET_DATE AS DATE)
        WHERE t.XD IN ({xd_literals})
        GROUP BY t.XD, t.TIME_15MIN
        ORDER BY t.XD, t.TIME_15MIN
        """

        series_map: Dict[int, List[Dict[str, Optional[float]]]] = defaultdict(list)
        time_records = session.sql(time_query).collect()
        for record in time_records:
            data = record.as_dict() if hasattr(record, "as_dict") else dict(record)
            try:
                xd = int(data.get("XD"))
            except (TypeError, ValueError):
                continue

            minutes = _minutes_from_value(data.get("TIME_15MIN"))
            if minutes is None:
                continue

            actual = _safe_float(data.get("AVG_ACTUAL"))
            forecast = _safe_float(data.get("AVG_PREDICTION"))
            if math.isnan(actual) and math.isnan(forecast):
                continue
            if math.isnan(actual):
                actual = None  # type: ignore[assignment]
            if math.isnan(forecast):
                forecast = None  # type: ignore[assignment]

            series_map[xd].append(
                {
                    "minutes": minutes,
                    "timestamp": _combine_date_minutes(yesterday, minutes),
                    "actual": actual,
                    "prediction": forecast,
                }
            )

        for row in rows:
            points = series_map.get(row["xd"], [])
            points.sort(key=lambda item: item["minutes"])
            row["time_of_day_series"] = points

        def _severity_sort_value(item: Dict[str, Any]) -> float:
            value = _safe_float(item.get("severity_score"))
            return value if math.isfinite(value) else float("-inf")

        rows.sort(
            key=lambda item: (_severity_sort_value(item), item.get("xd") or 0),
            reverse=True,
        )

        return rows, threshold

    return handle_auth_error_retry(execute_query)


def _format_timestamp_for_sql(value: Any) -> str:
    """Convert a timestamp value into a SQL-safe string."""
    if isinstance(value, datetime):
        value = _to_local_naive(value)
        formatted = value.strftime("%Y-%m-%d %H:%M:%S")
    else:
        formatted = str(value)
    return formatted.replace("'", "''")


def fetch_changepoint_detail_rows(xd: int, change_timestamp: Any) -> List[Dict[str, Any]]:
    """Pull raw travel time samples surrounding a changepoint."""
    xd_value = int(xd)
    timestamp_sql = _format_timestamp_for_sql(change_timestamp)

    set_variable_sql = f"SET CHANGE_TS = TO_TIMESTAMP_NTZ('{timestamp_sql}')"

    query = f"""
    SELECT
        t.TIMESTAMP,
        t.TRAVEL_TIME_SECONDS,
        CASE
            WHEN t.TIMESTAMP < $CHANGE_TS THEN 'before'
            ELSE 'after'
        END AS PERIOD
    FROM TRAVEL_TIME_ANALYTICS t
    WHERE t.XD = {xd_value}
      AND t.TIMESTAMP BETWEEN DATEADD('day', -7, $CHANGE_TS)
                          AND DATEADD('day', 7, $CHANGE_TS)
    ORDER BY t.TIMESTAMP
    """

    def execute_query() -> List[Dict[str, Any]]:
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise RuntimeError("Unable to establish database connection for changepoint detail")

        session.sql(set_variable_sql).collect()
        table = session.sql(query).to_arrow()
        if table.num_rows == 0:
            return []

        detail_rows: List[Dict[str, Any]] = []
        for record in table.to_pylist():
            timestamp = record.get("TIMESTAMP")
            if hasattr(timestamp, "to_pydatetime"):
                timestamp = timestamp.to_pydatetime()
            if isinstance(timestamp, datetime):
                timestamp = _to_local_naive(timestamp)
            period_value = str(record.get("PERIOD") or "").lower()
            detail_rows.append(
                {
                    "timestamp": timestamp,
                    "travel_time_seconds": _safe_float(record.get("TRAVEL_TIME_SECONDS")),
                    "period": period_value,
                }
            )

        return detail_rows

    return handle_auth_error_retry(execute_query)


def fetch_changepoint_hourly_series(xd: int, change_timestamp: Any) -> List[Dict[str, Any]]:
    """Fetch hourly averaged travel times around a changepoint directly from Snowflake."""
    xd_value = int(xd)
    timestamp_sql = _format_timestamp_for_sql(change_timestamp)

    set_variable_sql = f"SET CHANGE_TS = TO_TIMESTAMP_NTZ('{timestamp_sql}')"

    query = f"""
    SELECT
        DATE_TRUNC('HOUR', t.TIMESTAMP) AS HOUR_TS,
        AVG(t.TRAVEL_TIME_SECONDS) AS AVG_TRAVEL_TIME,
        CASE
            WHEN t.TIMESTAMP < $CHANGE_TS THEN 'before'
            ELSE 'after'
        END AS PERIOD
    FROM TRAVEL_TIME_ANALYTICS t
    WHERE t.XD = {xd_value}
      AND t.TIMESTAMP BETWEEN DATEADD('day', -7, $CHANGE_TS)
                          AND DATEADD('day', 7, $CHANGE_TS)
    GROUP BY 1, 3
    ORDER BY HOUR_TS
    """

    def execute_query() -> List[Dict[str, Any]]:
        session = get_snowflake_session(retry=True, max_retries=2)
        if not session:
            raise RuntimeError("Unable to establish database connection for changepoint hourly series")

        session.sql(set_variable_sql).collect()
        table = session.sql(query).to_arrow()
        if table.num_rows == 0:
            return []

        hourly_rows: List[Dict[str, Any]] = []
        for record in table.to_pylist():
            hour_ts = record.get("HOUR_TS")
            if hasattr(hour_ts, "to_pydatetime"):
                hour_ts = hour_ts.to_pydatetime()
            if isinstance(hour_ts, datetime):
                hour_ts = _to_local_naive(hour_ts)
            period_value = str(record.get("PERIOD") or "").lower()
            hourly_rows.append(
                {
                    "timestamp": hour_ts,
                    "travel_time_seconds": _safe_float(record.get("AVG_TRAVEL_TIME")),
                    "period": period_value,
                }
            )

        return hourly_rows

    return handle_auth_error_retry(execute_query)


def build_changepoint_date_series(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[Tuple[datetime, float]]]:
    """Group travel time samples by period and sort by timestamp."""
    before: List[Tuple[datetime, float]] = []
    after: List[Tuple[datetime, float]] = []

    for row in rows:
        timestamp = row.get("timestamp")
        if not isinstance(timestamp, datetime):
            continue

        value = _safe_float(row.get("travel_time_seconds"))
        if math.isnan(value):
            continue

        period = str(row.get("period") or "").lower()
        if period == "before":
            before.append((timestamp, value))
        elif period == "after":
            after.append((timestamp, value))

    before.sort(key=lambda item: item[0])
    after.sort(key=lambda item: item[0])

    return {"before": before, "after": after}


def build_changepoint_time_of_day_series(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[Tuple[int, float]]]:
    """Average travel time samples into minute-of-day buckets."""
    before_buckets: defaultdict[int, List[float]] = defaultdict(list)
    after_buckets: defaultdict[int, List[float]] = defaultdict(list)

    for row in rows:
        timestamp = row.get("timestamp")
        if not isinstance(timestamp, datetime):
            continue

        value = _safe_float(row.get("travel_time_seconds"))
        if math.isnan(value):
            continue

        minutes = timestamp.hour * 60 + timestamp.minute
        period = str(row.get("period") or "").lower()

        if period == "before":
            before_buckets[minutes].append(value)
        elif period == "after":
            after_buckets[minutes].append(value)

    def _bucket_to_series(buckets: defaultdict[int, List[float]]) -> List[Tuple[int, float]]:
        series: List[Tuple[int, float]] = []
        for minute, values in buckets.items():
            if not values:
                continue
            avg = sum(values) / len(values)
            series.append((minute, round(avg, 2)))
        return sorted(series, key=lambda item: item[0])

    return {
        "before": _bucket_to_series(before_buckets),
        "after": _bucket_to_series(after_buckets),
    }


def _y_padding(series_list: Sequence[Sequence[Tuple[Any, float]]]) -> Tuple[Optional[float], Optional[float]]:
    """Compute y-axis min/max with padding for smoother charts."""
    y_values: List[float] = []
    for series in series_list:
        y_values.extend(value for _, value in series)

    if not y_values:
        return None, None

    y_min = min(y_values)
    y_max = max(y_values)

    if math.isclose(y_min, y_max):
        padding = max(abs(y_max) * 0.05, 1.0)
    else:
        padding = (y_max - y_min) * 0.1

    return y_min - padding, y_max + padding


def _format_minutes_label(value: float) -> str:
    total_minutes = int(round(value))
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def _render_anomaly_chart(series: Sequence[Dict[str, Any]]) -> Optional[bytes]:
    """Render an anomaly chart plotting actual vs forecast travel times."""
    if plt is None or not series:
        return None

    timestamps: List[datetime] = []
    actual_values: List[float] = []
    forecast_values: List[float] = []

    for point in series:
        timestamp_obj = point.get("timestamp")
        dt_value: Optional[datetime] = None
        if isinstance(timestamp_obj, datetime):
            dt_value = timestamp_obj
        else:
            minutes = _minutes_from_value(point.get("minutes"))
            if minutes is not None:
                dt_value = _combine_date_minutes(_local_today(), minutes)

        if dt_value is None:
            continue

        actual = _safe_float(point.get("actual"))
        forecast = _safe_float(point.get("prediction"))

        timestamps.append(dt_value)
        actual_values.append(actual if math.isfinite(actual) else math.nan)
        forecast_values.append(forecast if math.isfinite(forecast) else math.nan)

    finite_actual = [value for value in actual_values if math.isfinite(value)]
    finite_forecast = [value for value in forecast_values if math.isfinite(value)]
    if not finite_actual and not finite_forecast:
        return None

    fig, ax = plt.subplots(figsize=(COMPOSITE_FIG_WIDTH_IN, ANOMALY_FIG_HEIGHT_IN), dpi=170)

    ax.plot(
        timestamps,
        actual_values,
        color=AFTER_SERIES_HEX,
        linewidth=2.6,
        label="Actual",
    )
    ax.plot(
        timestamps,
        forecast_values,
        color=BEFORE_SERIES_HEX,
        linewidth=2.2,
        label="Forecast",
    )

    actual_points = [(x, y) for x, y in zip(timestamps, actual_values) if math.isfinite(y)]
    forecast_points = [(x, y) for x, y in zip(timestamps, forecast_values) if math.isfinite(y)]
    y_min, y_max = _y_padding([actual_points, forecast_points])
    if y_min is not None and y_max is not None:
        ax.set_ylim(y_min, y_max)

    if timestamps:
        ax.set_xlim(min(timestamps), max(timestamps))

    if mdates is not None:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%I:%M %p"))
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
        fig.autofmt_xdate(rotation=0, ha="center")

    ax.set_ylabel("Travel Time (seconds)", fontsize=9)
    ax.set_xlabel("Time", fontsize=9)
    ax.grid(True, linestyle="--", alpha=0.25)
    ax.tick_params(axis="both", labelsize=9, pad=4)

    legend = ax.legend(loc="upper left", fontsize=9, frameon=False)
    legend.set_title(None)

    for spine_name in ("top", "right"):
        ax.spines[spine_name].set_visible(False)
    for spine_name in ("left", "bottom"):
        spine = ax.spines[spine_name]
        spine.set_color("#C2D3F1")
        spine.set_linewidth(1.0)

    fig.patch.set_alpha(0)
    fig.tight_layout()

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches=None)
    plt.close(fig)
    return buffer.getvalue()


def _render_changepoint_composite_chart(
    meta: Dict[str, Any],
    date_series: Dict[str, List[Tuple[datetime, float]]],
    time_series: Dict[str, List[Tuple[int, float]]],
) -> Optional[bytes]:
    """Render daily trend and time-of-day charts in a single figure."""
    if plt is None:
        return None

    before_dates = date_series.get("before") or []
    after_dates = date_series.get("after") or []
    before_time = time_series.get("before") or []
    after_time = time_series.get("after") or []

    if not (before_dates or after_dates or before_time or after_time):
        return None

    fig = plt.figure(figsize=(COMPOSITE_FIG_WIDTH_IN, COMPOSITE_FIG_HEIGHT_IN), dpi=170)
    grid = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.0], hspace=0.56)

    ax_trend = fig.add_subplot(grid[0])
    if before_dates:
        x_before, y_before = zip(*before_dates)
        ax_trend.plot(x_before, y_before, color=BEFORE_SERIES_HEX, linewidth=2.2, label="Before")
    if after_dates:
        x_after, y_after = zip(*after_dates)
        ax_trend.plot(x_after, y_after, color=AFTER_SERIES_HEX, linewidth=2.2, label="After")

    y_min, y_max = _y_padding([before_dates, after_dates])
    if y_min is not None and y_max is not None:
        ax_trend.set_ylim(y_min, y_max)
    ax_trend.set_title("Daily Trend (Hourly)", fontsize=9, fontweight="bold", pad=6, loc="left")
    ax_trend.grid(True, linestyle="--", alpha=0.25)
    ax_trend.tick_params(axis="both", labelsize=9, pad=6)
    if mdates is not None and (before_dates or after_dates):
        locator = mdates.AutoDateLocator(minticks=3, maxticks=5)
        ax_trend.xaxis.set_major_locator(locator)
        ax_trend.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        plt.setp(ax_trend.get_xticklabels(), rotation=0, ha="center")
    else:
        ax_trend.set_xlabel("Date", fontsize=10)
    if ax_trend.has_data():
        legend = ax_trend.legend(
            loc="center left",
            bbox_to_anchor=(1.03, 0.5),
            frameon=False,
            fontsize=9,
            handlelength=1.4,
            borderaxespad=0.0,
            ncol=1,
            columnspacing=1.0,
        )
        if legend:
            legend.set_in_layout(False)
            for line in legend.get_lines():
                line.set_linewidth(2.2)
    ax_trend.set_facecolor("white")

    ax_profile = fig.add_subplot(grid[1])
    if before_time:
        x_before_time, y_before_time = zip(*before_time)
        ax_profile.plot(x_before_time, y_before_time, color=BEFORE_SERIES_HEX, linewidth=2.2)
    if after_time:
        x_after_time, y_after_time = zip(*after_time)
        ax_profile.plot(x_after_time, y_after_time, color=AFTER_SERIES_HEX, linewidth=2.2)

    y_profile_min, y_profile_max = _y_padding([before_time, after_time])
    if y_profile_min is not None and y_profile_max is not None:
        ax_profile.set_ylim(y_profile_min, y_profile_max)
    ax_profile.set_xlim(0, 24 * 60)
    tick_minutes = list(range(0, 24 * 60 + 1, 240))
    ax_profile.set_xticks(tick_minutes)
    ax_profile.set_xticklabels([_format_minutes_label(tick) for tick in tick_minutes])
    ax_profile.set_title("Time of Day (15-minute)", fontsize=9, fontweight="bold", pad=5, loc="left")
    ax_profile.grid(True, linestyle="--", alpha=0.25)
    ax_profile.tick_params(axis="both", labelsize=9, pad=4)
    ax_profile.set_facecolor("white")

    for ax in (ax_trend, ax_profile):
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        for spine_name in ("left", "bottom"):
            spine = ax.spines[spine_name]
            spine.set_color("#C2D3F1")
            spine.set_linewidth(1.0)
        ax.tick_params(axis="both", colors="#4A5668")

    fig.text(0.035, 0.5, "Travel Time (seconds)", rotation="vertical", va="center", ha="center", fontsize=10)
    fig.subplots_adjust(left=0.11, right=0.82, top=0.92, bottom=0.12)

    fig.patch.set_alpha(0)

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches=None)
    plt.close(fig)
    return buffer.getvalue()


def _collect_chart_images(meta: Dict[str, Any], date_series: Dict[str, Any], time_series: Dict[str, Any]) -> Dict[str, bytes]:
    """Generate chart image bytes for the PDF."""
    if plt is None:
        return {}

    images: Dict[str, bytes] = {}

    composite_chart = _render_changepoint_composite_chart(meta, date_series, time_series)
    if composite_chart:
        images["combined_profile"] = composite_chart

    return images


def enrich_monitoring_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach detail samples, aggregated series, and charts to each row."""
    enriched: List[Dict[str, Any]] = []

    for row in rows:
        item = dict(row)
        detail_rows: List[Dict[str, Any]] = []
        hourly_rows: List[Dict[str, Any]] = []
        try:
            detail_rows = fetch_changepoint_detail_rows(item["xd"], item["timestamp"])
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"[WARN] Unable to fetch changepoint detail for XD {item.get('xd')}: {exc}")
        try:
            hourly_rows = fetch_changepoint_hourly_series(item["xd"], item["timestamp"])
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"[WARN] Unable to fetch hourly changepoint trend for XD {item.get('xd')}: {exc}")

        date_source = hourly_rows or detail_rows
        date_series = build_changepoint_date_series(date_source)
        time_series = build_changepoint_time_of_day_series(detail_rows)

        item["detail_rows"] = detail_rows
        item["hourly_rows"] = hourly_rows
        item["date_series"] = date_series
        item["time_series"] = time_series
        item["chart_images"] = _collect_chart_images(item, date_series, time_series)

        enriched.append(item)

    return enriched


def _quote_literal(value: Any) -> str:
    """Return a SQL-safe quoted literal."""
    text = str(value)
    escaped = text.replace("'", "''")
    return f"'{escaped}'"


def _format_signal_label(signal_id: Any, name: Optional[str]) -> str:
    """Combine signal ID and name for human-readable display."""
    identifier = str(signal_id).strip() or "--"
    label = (name or "").strip()
    if label and label != identifier:
        return f"{identifier} - {label}"
    return identifier


def _format_signal_preview(labels: Sequence[str], prefix: str, *, max_items: int = 3) -> str:
    """Create a short preview line listing the first few labels."""
    if not labels:
        return ""
    preview = list(labels[:max_items])
    remainder = len(labels) - len(preview)
    joined = ", ".join(preview)
    if remainder > 0:
        return f"{prefix}: {joined}, and {remainder} more"
    return f"{prefix}: {joined}"


def _build_signal_filter_display(filters: Dict[str, Any]) -> Dict[str, Any]:
    """Compute group and individual signal display data for summaries."""
    raw_selected = filters.get("selected_signals") or filters.get("signal_ids") or []
    normalized_ids: List[str] = []
    seen_ids: Set[str] = set()

    for value in raw_selected:
        text = str(value).strip()
        if not text or text in seen_ids:
            continue
        normalized_ids.append(text)
        seen_ids.add(text)

    explicit_groups_raw = filters.get("selected_signal_groups") or []
    explicit_groups = [
        str(group).strip() for group in explicit_groups_raw if str(group).strip()
    ]
    explicit_group_set = set(explicit_groups)

    display: Dict[str, Any] = {
        "groups": [],
        "individuals": [],
        "individual_count": 0,
        "missing_ids": [],
        "total_selected": len(normalized_ids),
        "metadata_resolved": False,
    }

    if not normalized_ids:
        return display

    maintained = str(filters.get("maintained_by") or "all").lower()
    id_sql = ", ".join(_quote_literal(sig) for sig in normalized_ids)
    conditions = [f"ID IN ({id_sql})"]
    if maintained == "odot":
        conditions.append("ODOT_MAINTAINED = TRUE")
    elif maintained == "others":
        conditions.append("ODOT_MAINTAINED = FALSE")

    metadata_query = f"""
    SELECT
        ID,
        COALESCE(DISTRICT, 'Unknown') AS DISTRICT,
        NAME
    FROM DIM_SIGNALS
    WHERE {' AND '.join(conditions)}
    ORDER BY DISTRICT, ID
    """

    def execute_query():
        session = get_snowflake_session(retry=True, max_retries=1)
        if not session:
            raise RuntimeError("Unable to establish database connection for filter metadata")
        return session.sql(metadata_query).collect()

    try:
        metadata_rows = handle_auth_error_retry(execute_query)
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"[WARN] Unable to fetch signal metadata for filter summary: {exc}")
        return display

    if not metadata_rows:
        return display

    metadata_by_id: Dict[str, Dict[str, Any]] = {}
    selected_by_district: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for row in metadata_rows:
        signal_id = str(row["ID"]).strip()
        district_value = row["DISTRICT"]
        district = str(district_value).strip() if district_value not in (None, "") else "Unknown"
        name = row["NAME"]
        meta = {"id": signal_id, "district": district or "Unknown", "name": name}
        metadata_by_id[signal_id] = meta

    missing_ids: List[str] = []
    for sig_id in normalized_ids:
        meta = metadata_by_id.get(sig_id)
        if not meta:
            missing_ids.append(sig_id)
            continue
        district = meta["district"]
        selected_by_district[district].append(meta)

    districts_needed = list(selected_by_district.keys())
    district_totals: Dict[str, int] = {}

    if districts_needed:
        try:
            district_list_sql = ", ".join(_quote_literal(d) for d in districts_needed)
            count_conditions: List[str] = []
            if maintained == "odot":
                count_conditions.append("ODOT_MAINTAINED = TRUE")
            elif maintained == "others":
                count_conditions.append("ODOT_MAINTAINED = FALSE")
            count_conditions.append(f"COALESCE(DISTRICT, 'Unknown') IN ({district_list_sql})")
            where_clause = "WHERE " + " AND ".join(count_conditions)
            counts_query = f"""
            SELECT
                COALESCE(DISTRICT, 'Unknown') AS DISTRICT,
                COUNT(*) AS TOTAL
            FROM DIM_SIGNALS
            {where_clause}
            GROUP BY COALESCE(DISTRICT, 'Unknown')
            """
            counts_rows = session.sql(counts_query).collect()
            for row in counts_rows:
                district_value = row["DISTRICT"]
                district = str(district_value).strip() if district_value not in (None, "") else "Unknown"
                total = row["TOTAL"]
                try:
                    district_totals[district or "Unknown"] = int(total) if total is not None else 0
                except (TypeError, ValueError):
                    district_totals[district or "Unknown"] = 0
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"[WARN] Unable to compute district totals for signal filters: {exc}")
            district_totals = {}

    full_group_set: Set[str] = set()
    for district, items in selected_by_district.items():
        if district in explicit_group_set:
            full_group_set.add(district)
            continue
        total = district_totals.get(district)
        if total and len(items) >= total:
            full_group_set.add(district)

    groups_ordered: List[str] = []
    added_groups: Set[str] = set()
    for group in explicit_groups:
        if group not in added_groups:
            groups_ordered.append(group)
            added_groups.add(group)
    for district in selected_by_district.keys():
        if district in full_group_set and district not in added_groups:
            groups_ordered.append(district)
            added_groups.add(district)

    individuals_meta: List[Dict[str, Any]] = []
    for sig_id in normalized_ids:
        meta = metadata_by_id.get(sig_id)
        if not meta:
            continue
        if meta["district"] in full_group_set:
            continue
        individuals_meta.append(meta)

    individual_labels: List[str] = []
    seen_labels: Set[str] = set()
    for meta in individuals_meta:
        label = _format_signal_label(meta["id"], meta.get("name"))
        if label in seen_labels:
            continue
        individual_labels.append(label)
        seen_labels.add(label)

    display["groups"] = groups_ordered
    display["individuals"] = individual_labels
    display["individual_count"] = len(individual_labels)
    display["missing_ids"] = missing_ids
    display["metadata_resolved"] = True
    return display


def _ensure_signal_filter_display(filters: Dict[str, Any]) -> Dict[str, Any]:
    """Return cached signal filter display info, computing if necessary."""
    cached = filters.get("_signal_filter_display")
    if isinstance(cached, dict):
        return cached
    display = _build_signal_filter_display(filters)
    filters["_signal_filter_display"] = display
    return display


def _filters_summary(filters: Dict[str, Any]) -> str:
    detection_date = filters.get("end_date") or "--"
    parts = [f"Detection Date: {detection_date}"]

    maintained = filters.get("maintained_by", "all")
    if maintained and maintained != "all":
        parts.append(f"Maintained By: {maintained}")

    approach = filters.get("approach")
    if approach:
        parts.append(f"Approach: {approach}")

    valid_geometry = filters.get("valid_geometry")
    if valid_geometry and valid_geometry != "all":
        parts.append(f"Valid Geometry: {valid_geometry}")

    severity_value = _safe_float(filters.get("changepoint_severity_threshold"))
    if math.isfinite(severity_value):
        parts.append(f"Changepoint Severity >= {severity_value:.1f}")

    display = _ensure_signal_filter_display(filters)
    if display.get("metadata_resolved"):
        if display["groups"]:
            parts.append(f"Signal Groups: {', '.join(display['groups'])}")
        if display["individual_count"]:
            preview = _format_signal_preview(display["individuals"], "Signals", max_items=2)
            if preview:
                parts.append(preview)
        elif display["groups"] and display["total_selected"]:
            parts.append(f"Signals: {display['total_selected']} selected")
    elif display["total_selected"]:
        parts.append(f"Signals: {display['total_selected']} selected")

    return " | ".join(parts)


def _filters_detail_lines(filters: Dict[str, Any]) -> List[str]:
    lines: List[str] = []

    maintained = filters.get("maintained_by", "all")
    if maintained and maintained != "all":
        lines.append(f"Maintained by: {maintained.upper()}")

    approach = filters.get("approach")
    if approach:
        lines.append(f"Approach: {approach}")

    valid_geometry = filters.get("valid_geometry")
    if valid_geometry and valid_geometry != "all":
        lines.append(f"Geometry: {valid_geometry}")

    selected_xds = filters.get("selected_xds") or []
    if selected_xds:
        lines.append(f"XD focus: {len(selected_xds)} selected")

    display = _ensure_signal_filter_display(filters)
    if display.get("metadata_resolved"):
        if display["groups"]:
            lines.append(f"Signal groups: {', '.join(display['groups'])}")
        if display["individual_count"]:
            preview = _format_signal_preview(display["individuals"], "Specific signals", max_items=5)
            if preview:
                lines.append(preview)
        elif not display["groups"] and display["total_selected"]:
            lines.append(f"Signals filtered: {display['total_selected']} IDs")
    elif display["total_selected"]:
        lines.append(f"Signals filtered: {display['total_selected']} IDs")

    threshold_display = _safe_float(filters.get("anomaly_monitoring_threshold"))
    if math.isfinite(threshold_display):
        lines.append(f"Anomaly score threshold: >= {threshold_display:.1f}")

    cp_threshold_display = _safe_float(filters.get("changepoint_severity_threshold"))
    if math.isfinite(cp_threshold_display):
        lines.append(f"Changepoint severity threshold: >= {cp_threshold_display:.1f}")

    return lines


if FPDF is not None:

    class MonitoringReportPDF(FPDF):
        """Custom PDF layout for monitoring reports."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._report_title = EMAIL_SENDER_NAME
            self._report_subtitle = ""
            self._footer_label = ""

        def set_report_metadata(self, title: str, subtitle: str, footer_label: str) -> None:
            self._report_title = title or EMAIL_SENDER_NAME
            self._report_subtitle = subtitle or ""
            self._footer_label = footer_label or ""

        def header(self) -> None:  # pragma: no cover - layout concern
            """Override default header to keep the top of each page clean."""
            return

        def footer(self) -> None:  # pragma: no cover - layout concern
            self.set_y(-22)
            self.set_draw_color(210, 210, 210)
            self.set_line_width(0.4)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())

            self.set_font("Helvetica", "I", 9)
            self.set_text_color(120, 120, 120)

            self.set_y(-18)
            if self._footer_label:
                self.cell(0, 6, self._footer_label, align="L")
            page_text = f"Page {self.page_no()} / {{nb}}"
            self.cell(0, 6, page_text, align="R")
            self.set_text_color(0, 0, 0)

else:  # pragma: no cover - executed only when dependency missing

    class MonitoringReportPDF:  # type: ignore
        def __init__(self, *_, **__):
            raise RuntimeError("fpdf2 package is required to generate monitoring reports")


def _ensure_space(pdf, required_height: float) -> None:
    """Add a new page if the remaining vertical space is insufficient."""
    if pdf.get_y() + required_height > pdf.page_break_trigger:
        pdf.add_page()


def _render_combined_chart_block(pdf, meta: Dict[str, Any], image_bytes: Optional[bytes]) -> None:
    """Render the combined daily trend and time-of-day charts within the PDF layout."""
    if not image_bytes:
        return

    content_width = pdf.w - pdf.l_margin - pdf.r_margin
    natural_width = COMPOSITE_FIG_WIDTH_IN * 72
    chart_width = min(content_width, natural_width)
    inner_margin = 16
    inner_width = max(chart_width - inner_margin * 2, 16)

    xd_label = _clean_text(meta.get("xd"), "--")
    road = _clean_text(meta.get("roadname"), "Unknown road")
    bearing_value = _clean_text(meta.get("bearing"))
    location_text = f"XD {xd_label} | {road}"
    if bearing_value:
        location_text = f"{location_text} - {bearing_value}"
    associated = _clean_text(meta.get("associated_signals"), "--")
    road_with_bearing = f"{road} ({bearing_value})" if bearing_value else road
    location_text = f"XD {xd_label} | {road_with_bearing} | Signal(s): {associated}"

    pdf.set_text_color(33, 60, 96)
    pdf.set_font("Helvetica", "B", 10)
    location_line_height = 10.5
    top_padding = 6
    bottom_padding = 5
    callout_height = 10.5
    stats_height = 8.5
    block_top_margin = 6

    cursor_x, cursor_y = pdf.get_x(), pdf.get_y()
    try:
        location_lines = pdf.multi_cell(
            inner_width,
            location_line_height,
            location_text,
            split_only=True,  # type: ignore[arg-type] - available in fpdf2
        )
    except TypeError:
        # Fallback for older fpdf versions without split_only support.
        location_lines = []
        for raw_line in location_text.split("\n"):
            words = raw_line.split()
            if not words:
                location_lines.append("")
                continue
            current_line = words[0]
            for word in words[1:]:
                candidate = f"{current_line} {word}"
                if pdf.get_string_width(candidate) <= inner_width:
                    current_line = candidate
                else:
                    location_lines.append(current_line)
                    current_line = word
            location_lines.append(current_line)
    pdf.set_xy(cursor_x, cursor_y)
    if not location_lines:
        location_lines = [location_text]
    location_line_count = len(location_lines)
    location_height = location_line_count * location_line_height
    info_height = top_padding + location_height + callout_height + stats_height + bottom_padding

    png_width_px: Optional[int] = None
    png_height_px: Optional[int] = None
    if isinstance(image_bytes, (bytes, bytearray)) and image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        try:
            png_width_px = int.from_bytes(image_bytes[16:20], "big")
            png_height_px = int.from_bytes(image_bytes[20:24], "big")
        except Exception:
            png_width_px = None
            png_height_px = None

    if png_width_px and png_height_px and png_width_px > 0:
        chart_height = chart_width * (png_height_px / png_width_px)
    else:
        chart_height = chart_width * COMPOSITE_FIG_RATIO

    total_height = block_top_margin + info_height + chart_height + 14

    _ensure_space(pdf, total_height)

    start_x = pdf.l_margin + (content_width - chart_width) / 2.0
    start_y = pdf.get_y() + block_top_margin
    pdf.set_y(start_y)

    pdf.set_draw_color(212, 226, 247)
    pdf.set_fill_color(245, 248, 255)
    pdf.set_line_width(0.8)
    pdf.rect(start_x, start_y, chart_width, info_height, "FD")

    text_x = start_x + inner_margin
    pdf.set_xy(text_x, start_y + top_padding)
    pdf.set_text_color(33, 60, 96)
    pdf.set_font("Helvetica", "B", 10)
    pdf.multi_cell(inner_width, 10.5, location_text)

    callout_text, _, _, callout_text_rgb = _trend_callout(meta.get("pct_change"))
    pdf.set_text_color(*callout_text_rgb)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_x(text_x)
    pdf.cell(inner_width, 10.5, callout_text, ln=1)

    observed_label = _localize_timestamp(meta.get("timestamp")) or "--"
    before_value = _seconds(meta.get("avg_before"))
    after_value = _seconds(meta.get("avg_after"))
    delta_value = _seconds(meta.get("avg_diff"))
    pdf.set_text_color(80, 86, 96)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_x(text_x)
    stats_line = (
        f"Observed AT: {observed_label} | Before {before_value} | After {after_value} | Delta {delta_value}"
    )
    pdf.cell(inner_width, 8.5, stats_line, ln=1)

    pdf.set_y(start_y + info_height)
    stream = io.BytesIO(image_bytes)
    chart_y = pdf.get_y()
    pdf.image(stream, x=start_x, y=chart_y, w=chart_width, type="PNG")

    border_color = (194, 211, 241)
    pdf.set_draw_color(*border_color)
    pdf.set_line_width(0.8)
    pdf.line(start_x, chart_y, start_x, chart_y + chart_height)
    pdf.line(start_x + chart_width, chart_y, start_x + chart_width, chart_y + chart_height)
    pdf.line(start_x, chart_y + chart_height, start_x + chart_width, chart_y + chart_height)

    pdf.set_y(chart_y + chart_height + 6)




def build_monitoring_pdf(
    filters: Dict[str, Any],
    changepoint_rows: Iterable[Dict[str, Any]],
    *,
    anomalies: Sequence[Dict[str, Any]] = (),
    joke: Optional[Dict[str, Any]] = None,
) -> bytes:
    if plt is None:
        raise RuntimeError(
            "Matplotlib is required to render monitoring report charts. "
            "Install the 'matplotlib' package in the application environment."
        )
    pdf = MonitoringReportPDF(orientation="P", unit="pt", format="A4")
    pdf.set_margins(36, 36, 36)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=60)

    pdf.set_report_metadata("", "", f"Prepared by {EMAIL_SENDER_NAME}")
    pdf.add_page()

    content_width = pdf.w - pdf.l_margin - pdf.r_margin

    anomaly_rows: List[Dict[str, Any]] = [dict(item) for item in anomalies] if anomalies else []
    if anomaly_rows:
        def _anomaly_severity(row: Dict[str, Any]) -> float:
            value = _safe_float(row.get("severity_score"))
            return value if math.isfinite(value) else float("-inf")

        anomaly_rows.sort(
            key=lambda item: (_anomaly_severity(item), item.get("xd") or 0),
            reverse=True,
        )

    for anomaly in anomaly_rows:
        series = anomaly.get("time_of_day_series") or []
        anomaly.setdefault("chart_image", _render_anomaly_chart(series))

    try:
        zone = ZoneInfo(TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        zone = None
    today = datetime.now(zone) if zone else datetime.utcnow()
    header_date = f"{today.strftime('%B')} {today.day}, {today.year}"

    banner_top = pdf.get_y()
    banner_height = 96
    pdf.set_fill_color(238, 244, 255)
    pdf.set_draw_color(194, 211, 241)
    pdf.set_line_width(0.9)
    pdf.rect(pdf.l_margin, banner_top, content_width, banner_height, "FD")

    pdf.set_xy(pdf.l_margin + 18, banner_top + 12)
    pdf.set_text_color(20, 46, 84)
    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(content_width - 36, 28, "Travel Time Analytics Report", ln=1)

    pdf.set_text_color(68, 88, 116)
    pdf.set_font("Helvetica", "", 13)
    pdf.set_x(pdf.l_margin + 18)
    pdf.cell(content_width - 36, 18, "Daily Performance Monitoring for Traffic Signals", ln=1)

    pdf.set_text_color(42, 72, 120)
    pdf.set_font("Helvetica", "I", 11)
    pdf.set_x(pdf.l_margin + 18)
    pdf.cell(content_width - 36, 16, header_date, ln=1)

    pdf.set_y(banner_top + banner_height + 14)
    pdf.set_text_color(64, 74, 94)
    pdf.set_font("Helvetica", "", 11)

    summary_paragraph = [
        ("This daily report monitors travel time anomalies and changepoints at traffic signals. It uses ", None),
        ("INRIX XD segment data", "https://github.com/ShawnStrasser/RITIS_INRIX_API"),
        (" delivered through the ", None),
        ("RITIS API", "https://github.com/ShawnStrasser/RITIS_INRIX_API"),
        (", is stored in ", None),
        ("Snowflake", "https://github.com/TPAU-ODOT/signal-analytics-snowflake"),
        (", and is analyzed with the ", None),
        ("traffic-anomaly toolkit", "https://github.com/ShawnStrasser/traffic-anomaly"),
        (". Explore the ", None),
        ("interactive dashboard", "https://signals.up.railway.app/"),
        (" or review the ", None),
        ("open-source codebase", "https://github.com/ShawnStrasser/signal-analytics-dashboard"),
        (" for implementation details.", None),
    ]
    _write_paragraph_with_links(pdf, summary_paragraph, line_height=15, base_color=(64, 74, 94))
    pdf.ln(10)

    pdf.set_line_width(0.4)
    pdf.set_draw_color(220, 220, 220)
    pdf.set_text_color(0, 0, 0)

    if joke:
        pdf.set_text_color(33, 60, 96)
        pdf.set_font("Helvetica", "B", 12)
        section_title = _clean_text(joke.get("section_title"), "Daily Humor")
        pdf.cell(0, 18, section_title, ln=1)
        pdf.set_text_color(70, 70, 76)
        pdf.set_font("Helvetica", "", 11)
        joke_text = _clean_text(joke.get("text"), "No joke available today.")
        _write_full_width(pdf, joke_text, 16)

        joke_image = joke.get("image")
        if isinstance(joke_image, (bytes, bytearray)):
            dimensions = joke.get("dimensions")
            width_px: Optional[float] = None
            height_px: Optional[float] = None

            if isinstance(dimensions, (tuple, list)) and len(dimensions) == 2:
                try:
                    width_px = float(dimensions[0])
                    height_px = float(dimensions[1])
                except (TypeError, ValueError):
                    width_px = None
                    height_px = None

            if not width_px or not height_px or width_px <= 0 or height_px <= 0:
                try:
                    width_px = float(joke.get("image_width"))
                    height_px = float(joke.get("image_height"))
                except (TypeError, ValueError):
                    width_px = None
                    height_px = None

            if not width_px or not height_px or width_px <= 0 or height_px <= 0:
                width_px, height_px = 600.0, 400.0

            max_page_width = pdf.w - pdf.l_margin - pdf.r_margin
            max_width_limit = min(max_page_width, float(JOKE_IMAGE_MAX_WIDTH_PT))
            max_height_limit = float(JOKE_IMAGE_MAX_HEIGHT_PT)

            scale_w = max_width_limit / width_px if width_px else 1.0
            scale_h = max_height_limit / height_px if height_px else 1.0
            raw_scale = min(scale_w, scale_h)
            if not math.isfinite(raw_scale) or raw_scale <= 0:
                raw_scale = 1.0
            applied_scale = min(raw_scale, 1.0)

            render_width = width_px * applied_scale
            render_height = height_px * applied_scale

            _ensure_space(pdf, render_height + 10)
            y_pos = pdf.get_y()
            pdf.image(io.BytesIO(joke_image), x=pdf.l_margin, y=y_pos, w=render_width, h=render_height, type="PNG")
            pdf.set_y(y_pos + render_height + 6)

        attribution_text = _clean_text(joke.get("attribution"))
        if not attribution_text:
            source_label = _clean_text(joke.get("source"))
            if source_label:
                attribution_text = f"Source: {source_label}"

        if attribution_text:
            pdf.set_font("Helvetica", "I", 9)
            _write_full_width(pdf, attribution_text, 12)

        pdf.ln(10)
    else:
        pdf.ln(6)

    pdf.set_text_color(41, 72, 132)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 18, "Your report has the following filters applied:", ln=1)
    detail_lines = _filters_detail_lines(filters)
    pdf.set_text_color(70, 70, 76)
    pdf.set_font("Helvetica", "", 10)
    if detail_lines:
        pdf.set_fill_color(242, 245, 253)
        pdf.set_draw_color(214, 222, 242)
        pdf.set_line_width(0.8)
        detail_text = "\n".join(f"- {line}" for line in detail_lines)
        pdf.multi_cell(content_width, 14, detail_text, border=1, fill=True)
        pdf.set_line_width(0.4)
    else:
        _write_full_width(pdf, "- No additional filters applied", 14)

    pdf.ln(8)
    _write_paragraph_with_links(
        pdf,
        [
            ("To adjust these filters, visit the ", None),
            ("monitoring page", "https://signals.up.railway.app/monitoring"),
            (".", None),
        ],
        line_height=12,
        base_color=(85, 90, 96),
    )
    pdf.ln(12)

    pdf.set_text_color(28, 54, 103)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 22, "Anomalies", ln=1)
    pdf.set_text_color(70, 70, 76)
    pdf.set_font("Helvetica", "", 11)
    anomaly_copy = (
        "An anomaly is when travel times are statistically higher than the forecast based on historical data. "
        "Anomalies may be caused by incidents, inclement weather, or temporary detection failure."
    )
    _write_full_width(pdf, anomaly_copy, 14)
    pdf.ln(6)

    if not anomaly_rows:
        pdf.set_text_color(85, 90, 96)
        pdf.set_font("Helvetica", "I", 11)
        _write_full_width(pdf, "No anomalies matched the current filters for yesterday.", 16)
        pdf.ln(6)
    else:
        pdf.set_text_color(70, 70, 76)
        pdf.set_font("Helvetica", "", 10)
        for index, anomaly in enumerate(anomaly_rows, start=1):
            chart_bytes = anomaly.get("chart_image")
            if chart_bytes:
                _render_anomaly_block(pdf, anomaly, chart_bytes)
            else:
                pdf.set_text_color(120, 120, 130)
                pdf.set_font("Helvetica", "I", 10)
                xd_label = _clean_text(anomaly.get("xd"), "--")
                _write_full_width(pdf, f"Unable to render anomaly chart for XD {xd_label}.", 14)
                pdf.set_text_color(70, 70, 76)
                pdf.set_font("Helvetica", "", 10)

            if index < len(anomaly_rows):
                pdf.ln(8)
        pdf.ln(6)

    pdf.set_text_color(28, 54, 103)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 22, "Changepoints", ln=1)
    pdf.set_text_color(70, 70, 76)
    pdf.set_font("Helvetica", "", 11)
    changepoint_blurb = (
        "A changepoint is when a structural shift occurs in travel time mean or variance, lasting more than a couple days. "
        "Changepoints may result from timing changes, construction, school starting, catastrophic detection failure, etc."
    )
    _write_full_width(pdf, changepoint_blurb, 14)
    pdf.ln(10)

    rows_list = list(changepoint_rows)
    if rows_list:
        def _changepoint_severity(row: Dict[str, Any]) -> float:
            severity_value = _safe_float(row.get("severity_score") or row.get("score"))
            if math.isfinite(severity_value):
                return severity_value
            pct_change = _safe_float(row.get("pct_change"))
            if math.isfinite(pct_change):
                return abs(pct_change)
            return float("-inf")

        rows_list.sort(
            key=lambda item: (_changepoint_severity(item), item.get("xd") or 0),
            reverse=True,
        )

    if not rows_list:
        pdf.set_font("Helvetica", "I", 12)
        _write_full_width(pdf, "No changepoints matched the current filters.", 16)
    else:
        for index, item in enumerate(rows_list, start=1):
            _ensure_space(pdf, 380)

            charts = item.get("chart_images") or {}
            composite_chart = charts.get("combined_profile")
            if composite_chart:
                _render_combined_chart_block(pdf, item, composite_chart)
            else:
                before_count = len(item.get("date_series", {}).get("before", []))
                after_count = len(item.get("date_series", {}).get("after", []))
                raise RuntimeError(
                    "Failed to render changepoint charts for "
                    f"XD {_clean_text(item.get('xd'), '--')} "
                    f"(before={before_count}, after={after_count})"
                )

            pdf.ln(2)
            if index < len(rows_list):
                pdf.ln(16)

    output = pdf.output(dest="S")
    return output.encode("latin-1") if isinstance(output, str) else output


def _render_anomaly_block(pdf, anomaly: Dict[str, Any], chart_bytes: Optional[bytes]) -> None:
    """Render a single anomaly summary with chart inside the PDF."""
    if not chart_bytes:
        return

    content_width = pdf.w - pdf.l_margin - pdf.r_margin
    natural_width = COMPOSITE_FIG_WIDTH_IN * 72
    chart_width = min(content_width, natural_width)
    inner_margin = 14
    text_width = max(chart_width - inner_margin * 2, 16)

    xd_label = _clean_text(anomaly.get("xd"), "--")
    road = _clean_text(anomaly.get("roadname"), "Unknown road")
    bearing_value = _clean_text(anomaly.get("bearing"))
    associated = _clean_text(anomaly.get("associated_signals"), "--")
    road_with_bearing = f"{road} ({bearing_value})" if bearing_value else road
    location_text = f"XD {xd_label} | {road_with_bearing} | Signal(s): {associated}"
    target_date = _coerce_date(anomaly.get("target_date"))
    if target_date:
        readable_date = _format_report_date(target_date)
        location_text = f"{location_text} - {readable_date}"

    location_line_height = 9.5
    top_padding = 6
    bottom_padding = 4
    block_top_margin = 4

    try:
        location_lines = pdf.multi_cell(
            text_width,
            location_line_height,
            location_text,
            split_only=True,  # type: ignore[arg-type]
        )
    except TypeError:
        location_lines = []

    if not location_lines:
        location_lines = [location_text]

    header_height = top_padding + len(location_lines) * location_line_height + bottom_padding

    png_width_px: Optional[int] = None
    png_height_px: Optional[int] = None
    if isinstance(chart_bytes, (bytes, bytearray)) and chart_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        try:
            png_width_px = int.from_bytes(chart_bytes[16:20], "big")
            png_height_px = int.from_bytes(chart_bytes[20:24], "big")
        except Exception:
            png_width_px = None
            png_height_px = None

    if png_width_px and png_height_px and png_width_px > 0:
        chart_height = chart_width * (png_height_px / png_width_px)
    else:
        chart_height = chart_width * 0.3

    total_height = block_top_margin + header_height + chart_height + 8
    _ensure_space(pdf, total_height)

    start_x = pdf.l_margin + (content_width - chart_width) / 2.0
    start_y = pdf.get_y() + block_top_margin

    # Header panel
    pdf.set_y(start_y)
    pdf.set_draw_color(212, 226, 247)
    pdf.set_fill_color(245, 248, 255)
    pdf.set_line_width(0.8)
    pdf.rect(start_x, start_y, chart_width, header_height, "FD")

    pdf.set_text_color(33, 60, 96)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_xy(start_x + inner_margin, start_y + top_padding)
    pdf.multi_cell(text_width, location_line_height, "\n".join(location_lines))

    # Chart image with blue outline
    chart_top = start_y + header_height
    pdf.image(io.BytesIO(chart_bytes), x=start_x, y=chart_top, w=chart_width, h=chart_height, type="PNG")
    pdf.set_draw_color(194, 211, 241)
    pdf.set_line_width(0.8)
    pdf.rect(start_x, chart_top, chart_width, chart_height)

    pdf.set_y(chart_top + chart_height + 4)


def build_email_html(
    filters: Dict[str, Any],
    changepoints: Iterable[Dict[str, Any]],
    *,
    anomalies: Sequence[Dict[str, Any]] = (),
    joke: Optional[Dict[str, Any]] = None,
    report_date: Optional[date] = None,
) -> str:
    changepoint_list = list(changepoints)
    anomaly_list = list(anomalies or [])
    changepoint_count = len(changepoint_list)
    anomaly_count = len(anomaly_list)
    changepoint_plural = "s" if changepoint_count != 1 else ""
    anomaly_plural = "ies" if anomaly_count != 1 else "y"
    resolved_report_date = report_date or _resolve_report_date(filters)
    readable_report_date = _format_report_date(resolved_report_date)

    anomaly_text = f"{anomaly_count} anomal{'y' if anomaly_count == 1 else 'ies'}"
    changepoint_text = f"{changepoint_count} changepoint{changepoint_plural}"

    html_output = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222;">
        <p>Hello,</p>
        <p>The attached traffic signal travel time analytics report for {readable_report_date} found {anomaly_text} and {changepoint_text}.</p>
        <p style="color:#9c4700;">Heads up: the interactive website is not launched yet, so any dashboard links referenced here or in the PDF won't work until it goes live.</p>
        <p style="margin-top:18px;">&mdash; {EMAIL_SENDER_NAME}</p>
    </div>
    """
    return html_output


def generate_and_send_report(email: str, raw_filters: Dict[str, Any], *, subject_prefix: str = "Monitoring Report") -> Dict[str, Any]:
    """Fetch monitoring data, generate a PDF, and send it via email."""
    filters = _parse_filters(raw_filters)
    start_date_value = str(filters.get("start_date") or "").strip()
    end_date_value = str(filters.get("end_date") or "").strip()
    if (
        start_date_value.lower() in {"", "none", "nat"}
        or end_date_value.lower() in {"", "none", "nat"}
    ):
        start_date, end_date = _default_monitoring_window()
        filters["start_date"] = start_date
        filters["end_date"] = end_date

    changepoint_rows = fetch_monitoring_rows(filters)
    anomaly_rows, resolved_threshold = fetch_monitoring_anomaly_rows(filters)
    filters["anomaly_monitoring_threshold"] = resolved_threshold

    if not changepoint_rows and not anomaly_rows:
        return {"sent": False, "reason": "no_data", "email": email}

    enriched_rows = enrich_monitoring_rows(changepoint_rows)
    report_date = _resolve_report_date(filters)
    joke = joke_service.prepare_joke(report_date)
    pdf_bytes = build_monitoring_pdf(filters, enriched_rows, anomalies=anomaly_rows, joke=joke)
    html_content = build_email_html(filters, enriched_rows, anomalies=anomaly_rows, report_date=report_date)
    subject = f"{subject_prefix} - {filters['end_date']}"

    if DEBUG_SAVE_REPORT_PDF:
        debug_dir = Path(BASE_DIR) / "debug_reports"
        debug_dir.mkdir(parents=True, exist_ok=True)
        safe_email = _clean_text(email, "recipient").replace("@", "_at_").replace(".", "_")
        timestamp_tag = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        filename = f"monitoring-report-{filters['end_date']}-{safe_email}-{timestamp_tag}.pdf"
        output_path = debug_dir / filename
        output_path.write_bytes(pdf_bytes)
        return {
            "sent": False,
            "reason": "debug_saved",
            "email": email,
            "rows": len(enriched_rows),
            "changepoints": len(enriched_rows),
            "anomalies": len(anomaly_rows),
            "debug_saved_path": str(output_path),
        }

    email_service.send_email(
        email,
        subject,
        html_content,
        attachments=[(f"monitoring-report-{filters['end_date']}.pdf", pdf_bytes)],
    )

    return {
        "sent": True,
        "email": email,
        "rows": len(enriched_rows),
        "changepoints": len(enriched_rows),
        "anomalies": len(anomaly_rows),
    }

def run_daily_dispatch() -> List[Dict[str, Any]]:
    """
    Iterate over all subscriptions and send monitoring reports.

    Returns a list of result dicts for observability.
    """
    subscription_store.cleanup_expired_artifacts()
    results: List[Dict[str, Any]] = []
    for subscription in subscription_store.list_subscriptions():
        email = subscription["email"]
        base_filters = subscription["settings"]
        filters = dict(base_filters) if isinstance(base_filters, dict) else {}
        start_date, end_date = _default_monitoring_window()
        filters["start_date"] = start_date
        filters["end_date"] = end_date
        if "selected_signals" not in filters and filters.get("signal_ids"):
            filters["selected_signals"] = filters["signal_ids"]
        report_date = _resolve_report_date(filters)
        dispatch_id = subscription_store.claim_daily_dispatch(email, report_date)
        if dispatch_id is None:
            results.append({"sent": False, "email": email, "reason": "duplicate_dispatch"})
            continue
        try:
            result = generate_and_send_report(email, filters, subject_prefix="Daily Monitoring Report")
        except Exception as exc:  # pragma: no cover - defensive logging
            subscription_store.finalize_daily_dispatch(dispatch_id, "failed", error=str(exc))
            results.append({"sent": False, "email": email, "error": str(exc)})
            continue
        status = "sent" if result.get("sent") else "skipped"
        reason = result.get("reason")
        subscription_store.finalize_daily_dispatch(dispatch_id, status, error=reason)
        results.append(result)
    return results

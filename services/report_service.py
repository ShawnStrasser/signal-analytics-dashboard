"""
Monitoring report data collection, PDF generation, and email delivery.
"""

from __future__ import annotations

import io
import math
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

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
    BASE_DIR,
    DAILY_REPORT_SEND_HOUR,
    DEBUG_SAVE_REPORT_PDF,
    EMAIL_SENDER_NAME,
    TIMEZONE,
)
from database import get_snowflake_session
from routes.api_changepoints import _assemble_where_clause  # pylint: disable=protected-access
from services import email_service, joke_service, subscription_store
from utils.query_utils import build_filter_joins_and_where, normalize_date


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
JOKE_IMAGE_MAX_WIDTH_PT = 6 * 72  # match ATSPM_Report scaling (approx 6 inches)
JOKE_IMAGE_MAX_HEIGHT_PT = 4 * 72  # approx 4 inches


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


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _localize_timestamp(timestamp: datetime) -> str:
    if not isinstance(timestamp, datetime):
        return str(timestamp)

    try:
        zone = ZoneInfo(TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        zone = None

    if zone:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=ZoneInfo("UTC"))
        timestamp = timestamp.astimezone(zone)
    return timestamp.strftime("%Y-%m-%d %H:%M")


def _parse_filters(raw_filters: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize incoming filter payload."""
    filters = {
        "start_date": normalize_date(raw_filters.get("start_date")),
        "end_date": normalize_date(raw_filters.get("end_date")),
        "signal_ids": raw_filters.get("signal_ids") or [],
        "selected_signals": raw_filters.get("selected_signals") or raw_filters.get("signal_ids") or [],
        "selected_xds": raw_filters.get("selected_xds") or [],
        "maintained_by": (raw_filters.get("maintained_by") or "all"),
        "approach": raw_filters.get("approach"),
        "valid_geometry": raw_filters.get("valid_geometry"),
    }

    improvement = raw_filters.get("pct_change_improvement", 0)
    degradation = raw_filters.get("pct_change_degradation", 0)

    try:
        filters["pct_change_improvement"] = abs(float(improvement))
    except (TypeError, ValueError):
        filters["pct_change_improvement"] = 0.0

    try:
        filters["pct_change_degradation"] = abs(float(degradation))
    except (TypeError, ValueError):
        filters["pct_change_degradation"] = 0.0

    return filters


def fetch_monitoring_rows(raw_filters: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
    """Query Snowflake for monitoring changepoints using the provided filters."""
    filters = _parse_filters(raw_filters)
    session = get_snowflake_session(retry=True, max_retries=2)
    if not session:
        raise RuntimeError("Unable to establish database connection for monitoring report")

    filter_join, filter_where = build_filter_joins_and_where(
        filters["signal_ids"],
        filters["maintained_by"],
        filters["approach"],
        filters["valid_geometry"],
    )

    needs_signal_join = "DIM_SIGNALS s" in filter_join
    join_signal_clause = "\n    INNER JOIN DIM_SIGNALS s ON xd.ID = s.ID" if needs_signal_join else ""

    where_clause = _assemble_where_clause(
        filters["start_date"],
        filters["end_date"],
        filter_where,
        filters["pct_change_improvement"],
        filters["pct_change_degradation"],
        selected_signals=filters["selected_signals"],
        selected_xds=filters["selected_xds"],
    )

    query = f"""
    SELECT
        t.XD AS XD,
        t.TIMESTAMP,
        t.PCT_CHANGE,
        t.AVG_DIFF,
        t.AVG_BEFORE,
        t.AVG_AFTER,
        t.SCORE,
        xd.ROADNAME,
        xd.BEARING
    FROM CHANGEPOINTS t
    INNER JOIN (
        SELECT DISTINCT XD, ID, ROADNAME, BEARING, APPROACH, VALID_GEOMETRY
        FROM DIM_SIGNALS_XD
    ) xd ON t.XD = xd.XD{join_signal_clause}
    WHERE {where_clause}
    ORDER BY ABS(t.PCT_CHANGE) DESC, t.TIMESTAMP DESC
    LIMIT {limit}
    """

    results = session.sql(query).collect()
    rows: List[Dict[str, Any]] = []

    for row in results:
        record = {
            "xd": row["XD"],
            "timestamp": row["TIMESTAMP"],
            "pct_change": row["PCT_CHANGE"],
            "avg_diff": row["AVG_DIFF"],
            "avg_before": row["AVG_BEFORE"],
            "avg_after": row["AVG_AFTER"],
            "score": row["SCORE"],
            "roadname": row["ROADNAME"],
            "bearing": row["BEARING"],
        }
        rows.append(record)

    return rows


def _format_timestamp_for_sql(value: Any) -> str:
    """Convert a timestamp value into a SQL-safe string."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def fetch_changepoint_detail_rows(xd: int, change_timestamp: Any) -> List[Dict[str, Any]]:
    """Pull raw travel time samples surrounding a changepoint."""
    session = get_snowflake_session(retry=True, max_retries=2)
    if not session:
        raise RuntimeError("Unable to establish database connection for changepoint detail")

    xd_value = int(xd)
    timestamp_sql = _format_timestamp_for_sql(change_timestamp)

    query = f"""
    WITH params AS (
        SELECT TO_TIMESTAMP('{timestamp_sql}') AS CHANGE_TS
    )
    SELECT
        t.TIMESTAMP,
        t.TRAVEL_TIME_SECONDS,
        CASE
            WHEN t.TIMESTAMP < params.CHANGE_TS THEN 'before'
            ELSE 'after'
        END AS PERIOD
    FROM TRAVEL_TIME_ANALYTICS t
    CROSS JOIN params
    WHERE t.XD = {xd_value}
      AND t.TIMESTAMP BETWEEN DATEADD('day', -7, params.CHANGE_TS)
                          AND DATEADD('day', 7, params.CHANGE_TS)
    ORDER BY t.TIMESTAMP
    """

    table = session.sql(query).to_arrow()
    if table.num_rows == 0:
        return []

    detail_rows: List[Dict[str, Any]] = []
    for record in table.to_pylist():
        timestamp = record.get("TIMESTAMP")
        if hasattr(timestamp, "to_pydatetime"):
            timestamp = timestamp.to_pydatetime()
        period_value = str(record.get("PERIOD") or "").lower()
        detail_rows.append(
            {
                "timestamp": timestamp,
                "travel_time_seconds": _safe_float(record.get("TRAVEL_TIME_SECONDS")),
                "period": period_value,
            }
        )

    return detail_rows


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

    fig = plt.figure(figsize=(6.8, 5.2), dpi=170)
    grid = fig.add_gridspec(2, 1, height_ratios=[1.15, 1], hspace=0.32)

    ax_trend = fig.add_subplot(grid[0])
    if before_dates:
        x_before, y_before = zip(*before_dates)
        ax_trend.plot(x_before, y_before, color=BEFORE_SERIES_HEX, linewidth=2.2)
    if after_dates:
        x_after, y_after = zip(*after_dates)
        ax_trend.plot(x_after, y_after, color=AFTER_SERIES_HEX, linewidth=2.2)

    y_min, y_max = _y_padding([before_dates, after_dates])
    if y_min is not None and y_max is not None:
        ax_trend.set_ylim(y_min, y_max)
    ax_trend.set_ylabel("Travel Time (seconds)", fontsize=10)
    ax_trend.set_title("Daily Trend", fontsize=12, pad=10)
    ax_trend.grid(True, linestyle="--", alpha=0.25)
    ax_trend.tick_params(axis="both", labelsize=9)
    if mdates is not None and (before_dates or after_dates):
        locator = mdates.AutoDateLocator()
        ax_trend.xaxis.set_major_locator(locator)
        ax_trend.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        plt.setp(ax_trend.get_xticklabels(), rotation=0, ha="center")
    else:
        ax_trend.set_xlabel("Date", fontsize=10)

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
    ax_profile.set_xlabel("Time of Day", fontsize=10)
    ax_profile.set_ylabel("Travel Time (seconds)", fontsize=10)
    ax_profile.set_title("Time of Day", fontsize=12, pad=10)
    ax_profile.grid(True, linestyle="--", alpha=0.25)
    ax_profile.tick_params(axis="both", labelsize=9)

    fig.subplots_adjust(left=0.12, right=0.98, top=0.95, bottom=0.1)

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
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
        try:
            detail_rows = fetch_changepoint_detail_rows(item["xd"], item["timestamp"])
        except Exception as exc:  # pragma: no cover - defensive logging
            print(f"[WARN] Unable to fetch changepoint detail for XD {item.get('xd')}: {exc}")

        date_series = build_changepoint_date_series(detail_rows)
        time_series = build_changepoint_time_of_day_series(detail_rows)

        item["detail_rows"] = detail_rows
        item["date_series"] = date_series
        item["time_series"] = time_series
        item["chart_images"] = _collect_chart_images(item, date_series, time_series)

        enriched.append(item)

    return enriched


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

    pct_improve = filters.get("pct_change_improvement", 0)
    pct_degrade = filters.get("pct_change_degradation", 0)
    parts.append(
        f"Percent Change Threshold: +{pct_degrade:.2f}% / {-pct_improve:.2f}%"
    )

    signals = filters.get("signal_ids") or []
    if signals:
        parts.append(f"Signals: {len(signals)} selected")

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

    signals = filters.get("signal_ids") or []
    if signals:
        lines.append(f"Signals filtered: {len(signals)} IDs")

    pct_improve = filters.get("pct_change_improvement", 0)
    pct_degrade = filters.get("pct_change_degradation", 0)
    lines.append(
        f"Requires >= {pct_degrade:.1f}% increase or <= {-pct_improve:.1f}% decrease in travel time"
    )

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


def _draw_legend_entry(pdf, x_pos: float, y_pos: float, label: str, color: Tuple[int, int, int]) -> float:
    """Draw a colored swatch with a label, returning the next x position."""
    box_size = 10
    pdf.set_fill_color(*color)
    pdf.rect(x_pos, y_pos, box_size, box_size, "F")
    pdf.set_text_color(62, 72, 85)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(x_pos + box_size + 4, y_pos - 1)
    pdf.cell(0, box_size + 2, label)
    return x_pos + box_size + 4 + pdf.get_string_width(label) + 12


def _render_combined_chart_block(pdf, meta: Dict[str, Any], image_bytes: Optional[bytes]) -> None:
    """Render the combined daily trend and time-of-day charts with a shared legend."""
    if not image_bytes:
        return

    chart_width = pdf.w - pdf.l_margin - pdf.r_margin
    chart_height = chart_width * 0.52
    info_height = 52
    total_height = info_height + chart_height + 14

    _ensure_space(pdf, total_height)

    start_x = pdf.l_margin
    start_y = pdf.get_y()

    pdf.set_draw_color(212, 226, 247)
    pdf.set_fill_color(245, 248, 255)
    pdf.set_line_width(0.8)
    pdf.rect(start_x, start_y, chart_width, info_height, "FD")

    pdf.set_text_color(33, 60, 96)
    pdf.set_font("Helvetica", "B", 11)
    xd_label = _clean_text(meta.get("xd"), "--")
    road = _clean_text(meta.get("roadname"), "Unknown road")
    pdf.set_xy(start_x + 12, start_y + 12)
    pdf.cell(chart_width - 24, 12, f"XD {xd_label} | {road}", ln=1)

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(80, 86, 96)
    details: List[str] = []
    timestamp = _localize_timestamp(meta.get("timestamp"))
    if timestamp:
        details.append(f"Observed: {timestamp}")
    bearing_value = _clean_text(meta.get("bearing"))
    if bearing_value:
        details.append(f"Bearing: {bearing_value}")
    info_text = " | ".join(details)
    pdf.set_xy(start_x + 12, start_y + 30)
    info_width = max(chart_width - 190, chart_width * 0.55)
    pdf.cell(info_width, 12, info_text or " ")

    legend_x = max(start_x + chart_width - 150, start_x + info_width + 24)
    legend_y = start_y + 16
    legend_next = _draw_legend_entry(pdf, legend_x, legend_y, "Before", BEFORE_SERIES_RGB)
    _draw_legend_entry(pdf, legend_next, legend_y, "After", AFTER_SERIES_RGB)

    pdf.set_y(start_y + info_height + 6)
    stream = io.BytesIO(image_bytes)
    pdf.image(stream, x=start_x, y=pdf.get_y(), w=chart_width, h=chart_height, type="PNG")
    pdf.set_y(pdf.get_y() + chart_height + 8)




def build_monitoring_pdf(
    filters: Dict[str, Any],
    rows: Iterable[Dict[str, Any]],
    joke: Optional[Dict[str, Any]] = None,
) -> bytes:
    if plt is None:
        raise RuntimeError(
            "Matplotlib is required to render monitoring report charts. "
            "Install the 'matplotlib' package in the application environment."
        )
    pdf = MonitoringReportPDF(orientation="P", unit="pt", format="A4")
    pdf.set_margins(54, 68, 54)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=60)

    detection_label = _clean_text(filters.get("end_date"), "--")
    pdf.set_report_metadata("", "", f"Prepared by {EMAIL_SENDER_NAME}")
    pdf.add_page()

    content_width = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_text_color(28, 45, 82)
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 28, f"Travel Time Analytics - {detection_label}", ln=1)

    pdf.set_font("Helvetica", "", 13)
    pdf.set_text_color(76, 92, 108)
    pdf.cell(0, 20, "Daily Performance Monitoring for Traffic Signals", ln=1)
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 11)
    summary_paragraph_1 = [
        ("This daily report monitors travel time anomalies and changepoints at traffic signals. It uses ", None),
        ("INRIX XD segment data", "https://github.com/ShawnStrasser/RITIS_INRIX_API"),
        (" delivered through the ", None),
        ("RITIS API", "https://github.com/ShawnStrasser/RITIS_INRIX_API"),
        (", is stored in ", None),
        ("Snowflake", "https://github.com/TPAU-ODOT/signal-analytics-snowflake"),
        (", and is analyzed with the ", None),
        ("traffic-anomaly toolkit", "https://github.com/ShawnStrasser/traffic-anomaly"),
        (".", None),
    ]
    _write_paragraph_with_links(pdf, summary_paragraph_1, line_height=14)

    summary_paragraph_2 = [
        ("Explore the ", None),
        ("interactive dashboard", "https://signals.up.railway.app/"),
        (" or review the ", None),
        ("open-source codebase", "https://github.com/ShawnStrasser/signal-analytics-dashboard"),
        (" for implementation details.", None),
    ]
    _write_paragraph_with_links(pdf, summary_paragraph_2, line_height=14)
    pdf.ln(4)

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

    pdf.ln(4)
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
    pdf.ln(6)

    pdf.set_line_width(0.4)
    pdf.set_draw_color(220, 220, 220)
    pdf.set_text_color(0, 0, 0)

    if joke:
        pdf.set_text_color(33, 60, 96)
        pdf.set_font("Helvetica", "B", 12)
        section_title = _clean_text(joke.get("section_title"), "Joke of the Week")
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

        pdf.ln(8)

    pdf.set_text_color(28, 54, 103)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 22, "Anomalies", ln=1)
    pdf.set_text_color(85, 90, 96)
    pdf.set_font("Helvetica", "I", 11)
    _write_full_width(pdf, "No Anomalies Today.", 16)
    pdf.ln(6)

    pdf.set_text_color(28, 54, 103)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 22, "Changepoints", ln=1)
    pdf.set_text_color(70, 70, 76)
    pdf.set_font("Helvetica", "", 11)
    changepoint_intro = [
        "We surface changepoints confirmed a week after detection so each highlight reflects a persistent structural shift in travel time.",
        "Use these insights to focus follow-up investigations on corridors where conditions have materially changed.",
    ]
    for line in changepoint_intro:
        _write_full_width(pdf, line, 14)
    pdf.ln(8)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 12)

    rows_list = list(rows)
    if not rows_list:
        pdf.set_font("Helvetica", "I", 12)
        _write_full_width(pdf, "No changepoints matched the current filters.", 16)
    else:
        for index, item in enumerate(rows_list, start=1):
            _ensure_space(pdf, 260)
            pdf.set_text_color(28, 54, 103)
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 16, f"{index}. Changepoint", ln=1)

            callout_text, fill_rgb, border_rgb, text_rgb = _trend_callout(item.get("pct_change"))
            pdf.set_fill_color(*fill_rgb)
            pdf.set_draw_color(*border_rgb)
            pdf.set_line_width(0.9)
            pdf.set_text_color(*text_rgb)
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(content_width, 20, callout_text, border=1, fill=True, align="C")
            pdf.ln(4)

            concise_metrics = [
                f"Change {_percent(item.get('pct_change'))}",
                f"Delta {_seconds(item.get('avg_diff'))}",
                f"Before {_seconds(item.get('avg_before'))}",
                f"After {_seconds(item.get('avg_after'))}",
            ]
            pdf.set_text_color(60, 63, 70)
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 12, " | ".join(concise_metrics), ln=1)
            pdf.ln(2)

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
                line_y = pdf.get_y()
                pdf.set_draw_color(215, 222, 232)
                try:
                    pdf.dashed_line(pdf.l_margin, line_y, pdf.w - pdf.r_margin, line_y, dash_length=3, space_length=2)
                except AttributeError:
                    pdf.line(pdf.l_margin, line_y, pdf.w - pdf.r_margin, line_y)
                pdf.ln(16)
            if index < len(rows_list):
                line_y = pdf.get_y()
                pdf.set_draw_color(215, 222, 232)
                try:
                    pdf.dashed_line(pdf.l_margin, line_y, pdf.w - pdf.r_margin, line_y, dash_length=3, space_length=2)
                except AttributeError:
                    pdf.line(pdf.l_margin, line_y, pdf.w - pdf.r_margin, line_y)
                pdf.ln(12)

    output = pdf.output(dest="S")
    return output.encode("latin-1") if isinstance(output, str) else output



def build_email_html(
    filters: Dict[str, Any],
    rows: Iterable[Dict[str, Any]],
    joke: Optional[Dict[str, Any]] = None,
) -> str:
    rows_list = list(rows)
    count = len(rows_list)
    plural = "s" if count != 1 else ""
    summary = _filters_summary(filters)
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    html_output = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222;">
        <p>Hello,</p>
        <p>Your monitoring report covering {summary} includes <strong>{count}</strong> changepoint{plural}. The PDF version is attached.</p>
        <p>Generated at {generated_at}.</p>
        <p style="margin-top:18px;">&mdash; {EMAIL_SENDER_NAME}</p>
    </div>
    """
    return html_output


def generate_and_send_report(email: str, raw_filters: Dict[str, Any], *, subject_prefix: str = "Monitoring Report") -> Dict[str, Any]:
    """Fetch monitoring data, generate a PDF, and send it via email."""
    filters = _parse_filters(raw_filters)
    rows = fetch_monitoring_rows(filters)
    if not rows:
        return {"sent": False, "reason": "no_data", "email": email}

    enriched_rows = enrich_monitoring_rows(rows)
    report_date = _resolve_report_date(filters)
    joke = joke_service.prepare_joke(report_date)
    pdf_bytes = build_monitoring_pdf(filters, enriched_rows, joke=joke)
    html_content = build_email_html(filters, enriched_rows)
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
            "debug_saved_path": str(output_path),
        }

    email_service.send_email(
        email,
        subject,
        html_content,
        attachments=[(f"monitoring-report-{filters['end_date']}.pdf", pdf_bytes)],
    )

    return {"sent": True, "email": email, "rows": len(enriched_rows)}

def run_daily_dispatch() -> List[Dict[str, Any]]:
    """
    Iterate over all subscriptions and send monitoring reports.

    Returns a list of result dicts for observability.
    """
    subscription_store.cleanup_expired_artifacts()
    results: List[Dict[str, Any]] = []
    for subscription in subscription_store.list_subscriptions():
        email = subscription["email"]
        filters = subscription["settings"]
        try:
            result = generate_and_send_report(email, filters, subject_prefix="Daily Monitoring Report")
        except Exception as exc:  # pragma: no cover - defensive logging
            results.append({"sent": False, "email": email, "error": str(exc)})
            continue
        results.append(result)
    return results

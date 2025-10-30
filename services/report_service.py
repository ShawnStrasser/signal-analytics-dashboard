"""
Monitoring report data collection, PDF generation, and email delivery.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

try:
    from fpdf import FPDF
except ImportError:  # pragma: no cover - optional dependency during testing
    FPDF = None  # type: ignore
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import (
    DAILY_REPORT_SEND_HOUR,
    EMAIL_SENDER_NAME,
    TIMEZONE,
)
from database import get_snowflake_session
from routes.api_changepoints import _assemble_where_clause  # pylint: disable=protected-access
from services import email_service, subscription_store
from utils.query_utils import build_filter_joins_and_where, normalize_date


def _percent(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"{float(value) * 100:.1f}%"


def _seconds(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"{float(value):.1f} s"


def _write_full_width(pdf, text: str, height: float) -> None:
    """Helper to render multi-line text using the full printable width."""
    pdf.set_x(pdf.l_margin)
    usable_width = pdf.w - pdf.l_margin - pdf.r_margin
    if usable_width <= 0:
        usable_width = pdf.w
    pdf.multi_cell(usable_width, height, text)


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


def _filters_summary(filters: Dict[str, Any]) -> str:
    parts = [
        f"Start: {filters.get('start_date', '--')}",
        f"End: {filters.get('end_date', '--')}",
    ]

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
    parts.append(f"Percent Change >= {pct_degrade:.2f} or <= {-pct_improve:.2f}")

    signals = filters.get("signal_ids") or []
    if signals:
        parts.append(f"Signals: {len(signals)} selected")

    return " | ".join(parts)


if FPDF is not None:

    class MonitoringReportPDF(FPDF):
        """Custom PDF layout for monitoring reports."""

        def header(self) -> None:  # pragma: no cover - layout concern
            self.set_font("Helvetica", "B", 16)
            self.cell(0, 10, EMAIL_SENDER_NAME, ln=1)
            self.ln(4)

else:  # pragma: no cover - executed only when dependency missing

    class MonitoringReportPDF:  # type: ignore
        def __init__(self, *_, **__):
            raise RuntimeError("fpdf2 package is required to generate monitoring reports")


def build_monitoring_pdf(filters: Dict[str, Any], rows: Iterable[Dict[str, Any]]) -> bytes:
    """Create a PDF document for the monitoring report."""
    pdf = MonitoringReportPDF(orientation="P", unit="pt", format="A4")
    pdf.set_auto_page_break(auto=True, margin=36)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 24, "Monitoring Report", ln=1)

    pdf.set_font("Helvetica", "", 12)
    _write_full_width(pdf, _filters_summary(filters), 16)
    pdf.ln(10)

    if not rows:
        pdf.set_font("Helvetica", "I", 12)
        _write_full_width(pdf, "No changepoints matched the current filters.", 16)
    else:
        for index, item in enumerate(rows, start=1):
            pdf.set_font("Helvetica", "B", 13)
            road = (item.get("roadname") or "Unknown road").replace("–", "-")
            title = f"{index}. XD {item.get('xd', '--')} - {road}"
            _write_full_width(pdf, title, 16)

            timestamp = _localize_timestamp(item.get("timestamp"))
            pdf.set_font("Helvetica", "", 11)
            _write_full_width(pdf, f"Timestamp: {timestamp}", 14)
            bearing_value = item.get("bearing")
            if bearing_value:
                _write_full_width(pdf, f"Bearing: {bearing_value}", 14)

            pdf.set_font("Helvetica", "", 10)
            pdf.set_fill_color(240, 240, 240)

            metrics = [
                ("Percent Change", _percent(item.get("pct_change"))),
                ("Average Difference", _seconds(item.get("avg_diff"))),
                ("Average Before", _seconds(item.get("avg_before"))),
                ("Average After", _seconds(item.get("avg_after"))),
            ]

            for label, value in metrics:
                pdf.cell(160, 16, label, border=1, align="L", fill=True)
                pdf.cell(0, 16, value, border=1, ln=1)

            pdf.ln(12)

    output = pdf.output(dest="S")
    return output.encode("latin-1") if isinstance(output, str) else output


def build_email_html(filters: Dict[str, Any], rows: Iterable[Dict[str, Any]]) -> str:
    """Generate a basic HTML summary suitable for email."""
    summary = _filters_summary(filters)

    rows_html = ""
    for item in rows:
        rows_html += f"""
            <tr>
                <td style="padding:6px 10px;border:1px solid #ddd;">XD {item.get('xd', '--')}</td>
                <td style="padding:6px 10px;border:1px solid #ddd;">{item.get('roadname') or '—'}</td>
                <td style="padding:6px 10px;border:1px solid #ddd;">{_localize_timestamp(item.get('timestamp'))}</td>
                <td style="padding:6px 10px;border:1px solid #ddd;">{_percent(item.get('pct_change'))}</td>
                <td style="padding:6px 10px;border:1px solid #ddd;">{_seconds(item.get('avg_diff'))}</td>
            </tr>
        """

    if not rows_html:
        rows_html = """
            <tr>
                <td colspan="5" style="padding:12px 10px;border:1px solid #ddd;text-align:center;">
                    No changepoints matched the selected filters for this period.
                </td>
            </tr>
        """

    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;color:#222;">
        <p>Hello,</p>
        <p>Here is your monitoring summary generated at {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}.</p>
        <p><strong>Filters:</strong> {summary}</p>
        <table style="border-collapse:collapse;width:100%;max-width:880px;margin-top:12px;">
            <thead>
                <tr style="background:#f0f0f0;">
                    <th style="padding:6px 10px;border:1px solid #ddd;text-align:left;">XD</th>
                    <th style="padding:6px 10px;border:1px solid #ddd;text-align:left;">Road</th>
                    <th style="padding:6px 10px;border:1px solid #ddd;text-align:left;">Timestamp</th>
                    <th style="padding:6px 10px;border:1px solid #ddd;text-align:left;">Pct Change</th>
                    <th style="padding:6px 10px;border:1px solid #ddd;text-align:left;">Avg Delta</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        <p style="margin-top:18px;">The full PDF version of this report is attached.</p>
        <p style="margin-top:18px;">— {EMAIL_SENDER_NAME}</p>
    </div>
    """
    return html


def generate_and_send_report(email: str, raw_filters: Dict[str, Any], *, subject_prefix: str = "Monitoring Report") -> Dict[str, Any]:
    """
    Fetch monitoring data, generate a PDF, and send it via email.

    Returns a dictionary describing the outcome, including whether an email was sent.
    """
    filters = _parse_filters(raw_filters)
    rows = fetch_monitoring_rows(filters)
    if not rows:
        return {"sent": False, "reason": "no_data", "email": email}

    pdf_bytes = build_monitoring_pdf(filters, rows)
    html_content = build_email_html(filters, rows)
    subject = f"{subject_prefix} – {filters['end_date']}"

    email_service.send_email(
        email,
        subject,
        html_content,
        attachments=[(f"monitoring-report-{filters['end_date']}.pdf", pdf_bytes)],
    )

    return {"sent": True, "email": email, "rows": len(rows)}


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

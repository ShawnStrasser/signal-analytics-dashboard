"""
INRIX algorithm change API routes (JSON). Events are detected from CHANGEPOINTS.

GET /api/algorithm-changes?start_date=&end_date=
    Events whose [start_date, end_date] span overlaps the range (both optional).
GET /api/algorithm-changes/report-impact?report_date=
    Which monitoring report sections are left out for a report date, plus the note text
    shown at the top of the PDF/email (used by the Monitoring page preview).
"""

from datetime import date

from flask import Blueprint, jsonify, request

from services import algorithm_changes
from utils.query_utils import normalize_date

algorithm_changes_bp = Blueprint('algorithm_changes', __name__)


def _optional_date(name):
    value = request.args.get(name)
    if value is None or not str(value).strip():
        return None
    return normalize_date(value)


@algorithm_changes_bp.route('/algorithm-changes', methods=['GET'])
def get_algorithm_changes():
    start_date = _optional_date('start_date')
    end_date = _optional_date('end_date')
    try:
        events = algorithm_changes.fetch_algorithm_changes(start_date, end_date)
    except Exception as exc:
        print(f"[ERROR] /algorithm-changes: {exc}")
        return jsonify({"error": "Algorithm changes are unavailable", "events": []}), 502
    return jsonify({
        "events": [algorithm_changes.serialize_event(event) for event in events],
    })


@algorithm_changes_bp.route('/algorithm-changes/report-impact', methods=['GET'])
def get_report_impact():
    from services.report_service import _local_today  # local import: avoids loading report deps at startup

    raw = _optional_date('report_date')
    report_date = date.fromisoformat(raw) if raw else _local_today()
    impact = algorithm_changes.report_impact(report_date)
    return jsonify({
        "report_date": report_date.isoformat(),
        "section_days": {key: value.isoformat() for key, value in impact["section_days"].items()},
        "excluded_sections": [key for key in algorithm_changes.REPORT_SECTION_ORDER if key in impact["excluded"]],
        "excluded_text": impact["excluded_text"],
        "notes": impact["notes"],
        "events": [algorithm_changes.serialize_event(event) for event in impact["events"]],
        "error": impact["error"],
    })

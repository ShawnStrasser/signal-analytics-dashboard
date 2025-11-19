"""
Monitoring subscription and report-related endpoints.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence

from flask import Blueprint, jsonify, request

from services import report_service, subscription_store
from routes.api_auth import SESSION_COOKIE_NAME  # reuse the same cookie name

subscriptions_bp = Blueprint("subscriptions", __name__)

_STRING_LIST_KEYS = {
    "signal_ids",
    "selected_signals",
    "selected_signal_groups",
    "selected_districts",
}
_INT_LIST_KEYS = {"selected_xds"}
_STRING_KEYS = {"maintained_by", "approach", "valid_geometry"}
_BOOL_KEYS = {"remove_anomalies"}
_FLOAT_KEYS = {
    "anomaly_monitoring_threshold",
    "changepoint_severity_threshold",
}


def _dedupe_preserve_order(items: Iterable[Any]) -> Sequence[Any]:
    seen = set()
    ordered = []
    for value in items:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _coerce_string_list(value: Any) -> Sequence[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        source = value
    else:
        source = [value]
    cleaned = []
    for item in source:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return _dedupe_preserve_order(cleaned)


def _coerce_int_list(value: Any) -> Sequence[int]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        source = value
    else:
        source = [value]
    cleaned = []
    for item in source:
        if item is None:
            continue
        try:
            cleaned.append(int(item))
        except (TypeError, ValueError):
            continue
    return _dedupe_preserve_order(cleaned)


def _sanitize_subscription_settings(raw_settings: Dict[str, Any]) -> Dict[str, Any]:
    """Persist only the filters that affect the automated report."""
    sanitized: Dict[str, Any] = {}

    for key in _STRING_LIST_KEYS:
        values = _coerce_string_list(raw_settings.get(key))
        if values:
            sanitized[key] = list(values)

    for key in _INT_LIST_KEYS:
        values = _coerce_int_list(raw_settings.get(key))
        if values:
            sanitized[key] = list(values)

    for key in _STRING_KEYS:
        value = raw_settings.get(key)
        if isinstance(value, str) and value.strip():
            sanitized[key] = value.strip()

    for key in _BOOL_KEYS:
        value = raw_settings.get(key)
        if isinstance(value, bool):
            sanitized[key] = value

    for key in _FLOAT_KEYS:
        value = raw_settings.get(key)
        if value is None:
            continue
        try:
            sanitized[key] = float(value)
        except (TypeError, ValueError):
            continue

    # Ensure consistency between signal_ids and selected_signals, if either is present.
    if "signal_ids" in sanitized and "selected_signals" not in sanitized:
        sanitized["selected_signals"] = list(sanitized["signal_ids"])
    elif "selected_signals" in sanitized and "signal_ids" not in sanitized:
        sanitized["signal_ids"] = list(sanitized["selected_signals"])

    return sanitized


def _current_user_email() -> Optional[str]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    session = subscription_store.get_session(token)
    if not session:
        return None
    return session["email"]


def _require_auth():
    email = _current_user_email()
    if not email:
        return None, jsonify({"error": "Authentication required"}), 401
    return email, None, None


@subscriptions_bp.route("/subscriptions", methods=["POST"])
def save_subscription():
    """Create or update a monitoring subscription for the current user."""
    email, error_response, status = _require_auth()
    if error_response:
        return error_response, status

    payload = request.get_json(silent=True) or {}
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        return jsonify({"error": "Invalid settings payload"}), 400

    sanitized_settings = _sanitize_subscription_settings(settings)
    subscription_store.upsert_subscription(email, sanitized_settings)
    return jsonify({"email": email, "settings": sanitized_settings, "subscribed": True})


@subscriptions_bp.route("/subscriptions", methods=["DELETE"])
def delete_subscription():
    """Remove the subscription for the current user."""
    email, error_response, status = _require_auth()
    if error_response:
        return error_response, status

    subscription_store.delete_subscription(email)
    return jsonify({"email": email, "subscribed": False})


@subscriptions_bp.route("/reports/send-test", methods=["POST"])
def send_test_report():
    """Generate and email a monitoring report immediately for the current user."""
    email, error_response, status = _require_auth()
    if error_response:
        return error_response, status

    _ = request.get_json(silent=True) or {}
    subscription = subscription_store.get_subscription(email)
    saved_settings = None
    if subscription and isinstance(subscription.get("settings"), dict):
        saved_settings = dict(subscription["settings"])

    if not saved_settings:
        return (
            jsonify(
                {
                    "error": "No saved subscription. Save your report filters before sending a test email.",
                }
            ),
            400,
        )

    effective_settings = saved_settings

    result = report_service.generate_and_send_report(
        email,
        effective_settings,
        subject_prefix="Monitoring Report (Test)",
    )
    if not result.get("sent"):
        reason = result.get("reason")
        if reason == "no_data":
            return jsonify({"message": "No changepoints matched the selected filters. Email not sent."}), 200
        if reason == "debug_saved":
            return jsonify({
                "message": f"Report saved locally at {result.get('debug_saved_path')}",
                "rows": result.get("rows", 0)
            }), 200
        return jsonify({"message": "Report generation failed.", "error": reason or "unknown"}), 500

    return jsonify({"message": "Test email sent", "rows": result.get("rows", 0)})

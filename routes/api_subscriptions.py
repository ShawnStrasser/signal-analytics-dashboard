"""
Monitoring subscription and report-related endpoints.
"""

from __future__ import annotations

from typing import Optional

from flask import Blueprint, jsonify, request

from services import report_service, subscription_store
from routes.api_auth import SESSION_COOKIE_NAME  # reuse the same cookie name

subscriptions_bp = Blueprint("subscriptions", __name__)


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

    subscription_store.upsert_subscription(email, settings)
    return jsonify({"email": email, "settings": settings, "subscribed": True})


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

    payload = request.get_json(silent=True) or {}
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        return jsonify({"error": "Invalid settings payload"}), 400

    result = report_service.generate_and_send_report(email, settings, subject_prefix="Monitoring Report (Test)")
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

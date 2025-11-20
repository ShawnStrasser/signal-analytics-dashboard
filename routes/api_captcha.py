"""
Captcha session management endpoints.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, make_response, request

from services import captcha_sessions
from services.rate_limiter import rate_limiter

captcha_bp = Blueprint("captcha", __name__)

# Reasonable defaults, can be tuned by ops
CAPTCHA_START_LIMIT = (20, 10 * 60)  # 20 requests per 10 minutes
CAPTCHA_VERIFY_LIMIT = (10, 60)      # 10 attempts per minute
EXPECTED_FINAL_STATE = ["red", "yellow", "green"]
EXPECTED_FINAL_STATE_SET = set(EXPECTED_FINAL_STATE)


def _client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _rate_limit(key: str, limit: int, window_seconds: int):
    allowed, retry_after = rate_limiter.allow(key, limit, window_seconds)
    if allowed:
        return None
    wait_seconds = max(1, int(retry_after or window_seconds))
    response = jsonify({"error": "Too many captcha attempts. Please slow down."})
    response.headers["Retry-After"] = str(wait_seconds)
    return response, 429


def _set_captcha_cookie(response, token: str):
    response.set_cookie(
        captcha_sessions.CAPTCHA_COOKIE_NAME,
        token,
        httponly=True,
        secure=request.is_secure,
        samesite="Strict",
        path="/",
    )


def _normalize_color(value: str | None):
    if not isinstance(value, str):
        return None
    return value.strip().lower()


def _final_state_is_valid(final_state) -> bool:
    if not isinstance(final_state, list) or len(final_state) != len(EXPECTED_FINAL_STATE):
        return False
    normalized = [_normalize_color(item) for item in final_state]
    return normalized == EXPECTED_FINAL_STATE


def _validate_metrics(meta: captcha_sessions.CaptchaNonce, metrics):
    if not isinstance(metrics, dict):
        return False, "missing_metrics"
    placement_order = metrics.get("placement_order")
    try:
        total_distance = float(metrics.get("total_distance", 0))
        elapsed_ms = int(metrics.get("elapsed_ms", 0))
        move_events = int(metrics.get("move_events", 0))
    except (TypeError, ValueError):
        return False, "invalid_metrics"
    if not isinstance(placement_order, list):
        return False, "invalid_metrics"
    normalized_order = {_normalize_color(item) for item in placement_order if isinstance(item, str)}
    if total_distance < meta.min_drag_distance:
        return False, "insufficient_drag"
    if elapsed_ms < meta.min_duration_ms:
        return False, "insufficient_duration"
    if move_events < meta.min_move_events:
        return False, "insufficient_motion"
    if normalized_order != EXPECTED_FINAL_STATE_SET:
        return False, "incomplete_puzzle"
    return True, None


@captcha_bp.route("/captcha/start", methods=["POST"])
def start_captcha():
    """Issue a captcha nonce so the frontend can render the puzzle."""
    ip = _client_ip()
    limit = _rate_limit(f"captcha:start:{ip}", *CAPTCHA_START_LIMIT)
    if limit:
        return limit
    nonce = captcha_sessions.create_nonce(ip)
    return jsonify({"nonce": nonce})


@captcha_bp.route("/captcha/verify", methods=["POST"])
def verify_captcha():
    """
    Validate the submitted nonce and, if successful, issue a signed captcha token cookie.
    """
    ip = _client_ip()
    limit = _rate_limit(f"captcha:verify:{ip}", *CAPTCHA_VERIFY_LIMIT)
    if limit:
        return limit

    payload = request.get_json(silent=True) or {}
    nonce = payload.get("nonce")
    metrics = payload.get("metrics")
    final_state = payload.get("final_state")
    if not isinstance(nonce, str) or len(nonce) < 10:
        return jsonify({"error": "invalid_nonce"}), 400

    meta = captcha_sessions.consume_nonce(nonce)
    if not meta or meta.client_ip != ip:
        return jsonify({"error": "invalid_or_expired_nonce"}), 400

    metrics_valid, metrics_error = _validate_metrics(meta, metrics)
    if not metrics_valid:
        return jsonify({"error": metrics_error or "invalid_metrics"}), 400

    if not _final_state_is_valid(final_state):
        return jsonify({"error": "invalid_final_state"}), 400

    token = captcha_sessions.generate_token(nonce)
    response = make_response(jsonify({"status": "verified"}))
    _set_captcha_cookie(response, token)
    return response


@captcha_bp.route("/captcha/status", methods=["GET"])
def captcha_status():
    """Lightweight endpoint for clients to check whether they are verified."""
    return jsonify({"verified": captcha_sessions.is_verified(request)})

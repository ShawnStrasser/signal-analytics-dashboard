"""
Authentication endpoints providing email-based magic-link login for monitoring.
"""

from __future__ import annotations

import secrets
from email.utils import parseaddr
from typing import Optional

from flask import Blueprint, jsonify, make_response, request
from utils.client_identity import get_client_id

from config import (
    PUBLIC_BASE_URL,
    SESSION_TTL_DAYS,
)
from services import email_service, subscription_store
from services.rate_limiter import rate_limiter

auth_bp = Blueprint("auth", __name__)

PUBLIC_AGENCY_SUFFIXES = (".gov", ".us")
PUBLIC_AGENCY_EXCEPTIONS = {"cityofsalem.net", "cityofmedford.org"}

SESSION_COOKIE_NAME = "monitoring_session"
EMAIL_REQUESTS_PER_DAY = 3
EMAIL_DAILY_WINDOW_SECONDS = 24 * 60 * 60
EMAIL_SHORT_WINDOW_LIMIT = 1
EMAIL_SHORT_WINDOW_SECONDS = 60



def _validate_email(email: Optional[str]) -> str:
    if not email:
        raise ValueError("Email is required")
    parsed = parseaddr(email)[1]
    if not parsed or "@" not in parsed:
        raise ValueError("Invalid email address")
    normalized = parsed.lower()
    domain = normalized.rsplit("@", 1)[-1]
    allowed_suffix = any(domain.endswith(suffix) for suffix in PUBLIC_AGENCY_SUFFIXES)
    if not allowed_suffix and domain not in PUBLIC_AGENCY_EXCEPTIONS:
        raise ValueError("A public agency email address is required")
    return normalized


def _build_login_link(token: str) -> str:
    """Construct the URL used in email magic links."""
    if PUBLIC_BASE_URL:
        base = PUBLIC_BASE_URL.rstrip("/")
    else:
        base = request.host_url.rstrip("/")
    return f"{base}/monitoring?loginToken={token}"


def _get_session_email() -> Optional[str]:
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_token:
        return None
    session = subscription_store.get_session(session_token)
    if not session:
        return None
    return session["email"]


def _set_session_cookie(response, token: str):
    max_age = None
    if SESSION_TTL_DAYS is not None:
        max_age = SESSION_TTL_DAYS * 24 * 60 * 60
    secure = request.is_secure
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        secure=secure,
        samesite="Lax",
        max_age=max_age,
    )


def _clear_session_cookie(response):
    response.delete_cookie(SESSION_COOKIE_NAME, samesite="Lax")


@auth_bp.route("/auth/request-link", methods=["POST"])
def request_magic_link():
    """Send a login link to the supplied email address."""
    payload = request.get_json(silent=True) or {}
    try:
        email = _validate_email(payload.get("email", ""))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # Daily per-email limit (in-memory, resets on restart)
    daily_key = f"magic-link-email-daily:{email}"
    allowed_daily, retry_after_daily = rate_limiter.allow(
        daily_key, EMAIL_REQUESTS_PER_DAY, EMAIL_DAILY_WINDOW_SECONDS
    )
    if not allowed_daily:
        wait_seconds = max(1, int(retry_after_daily or EMAIL_DAILY_WINDOW_SECONDS))
        response = jsonify({"error": "Too many login link requests today. Please try again tomorrow."})
        response.headers["Retry-After"] = str(wait_seconds)
        return response, 429

    # Short burst protection per email address
    email_key = f"magic-link-email:{email}"
    allowed, retry_after = rate_limiter.allow(email_key, EMAIL_SHORT_WINDOW_LIMIT, EMAIL_SHORT_WINDOW_SECONDS)
    if not allowed:
        wait_seconds = max(1, int(retry_after or EMAIL_SHORT_WINDOW_SECONDS))
        response = jsonify({"error": "Too many login link requests. Please wait before trying again."})
        response.headers["Retry-After"] = str(wait_seconds)
        return response, 429

    # Throttle repeated attempts from the same client IP
    client_id = get_client_id()
    client_key = f"magic-link-client:{client_id}"
    allowed_client, retry_after_client = rate_limiter.allow(client_key, 5, 60)
    if not allowed_client:
        wait_seconds = max(1, int(retry_after_client or EMAIL_SHORT_WINDOW_SECONDS))
        response = jsonify({"error": "Too many requests from this client. Please slow down."})
        response.headers["Retry-After"] = str(wait_seconds)
        return response, 429

    token = secrets.token_urlsafe(32)
    subscription_store.store_login_token(email, token)

    login_url = _build_login_link(token)
    html_content = f"""
        <p>Hello,</p>
        <p>Use the link below to sign in to the Signal Monitoring dashboard:</p>
        <p><a href="{login_url}">Sign in to Signal Monitoring</a></p>
        <p>This link expires soon and can only be used once.</p>
    """

    email_service.send_email(
        email,
        "Your monitoring sign-in link",
        html_content,
    )

    return jsonify({"message": "Login link sent"})


@auth_bp.route("/auth/verify", methods=["POST"])
def verify_magic_link():
    """Exchange a token from the login email for a persistent session cookie."""
    payload = request.get_json(silent=True) or {}
    token = payload.get("token")
    if not token:
        return jsonify({"error": "Missing token"}), 400

    email = subscription_store.consume_login_token(token)
    if not email:
        return jsonify({"error": "Invalid or expired token"}), 400

    session_token = subscription_store.create_session(email)
    subscription = subscription_store.get_subscription(email)

    response = make_response(
        jsonify(
            {
                "authenticated": True,
                "email": email,
                "subscribed": subscription is not None,
                "settings": subscription["settings"] if subscription else None,
            }
        )
    )
    _set_session_cookie(response, session_token)
    return response


@auth_bp.route("/auth/session", methods=["GET"])
def current_session():
    """Return session information if the user is authenticated."""
    email = _get_session_email()
    if not email:
        # Return 200 to avoid noisy console errors on the frontend. The payload still
        # includes an error flag so callers maintain the same control flow.
        return jsonify({"authenticated": False, "error": "Not authenticated"}), 200

    subscription = subscription_store.get_subscription(email)
    return jsonify(
        {
            "authenticated": True,
            "email": email,
            "subscribed": subscription is not None,
            "settings": subscription["settings"] if subscription else None,
        }
    )


@auth_bp.route("/auth/session", methods=["DELETE"])
def logout():
    """Terminate the active session."""
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if session_token:
        subscription_store.delete_session(session_token)
    response = make_response(jsonify({"message": "Logged out"}))
    _clear_session_cookie(response)
    return response

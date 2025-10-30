"""
Authentication endpoints providing email-based magic-link login for monitoring.
"""

from __future__ import annotations

import secrets
from email.utils import parseaddr
from typing import Optional

from flask import Blueprint, jsonify, make_response, request

from config import (
    PUBLIC_BASE_URL,
    SESSION_TTL_DAYS,
)
from services import email_service, subscription_store

auth_bp = Blueprint("auth", __name__)

SESSION_COOKIE_NAME = "monitoring_session"


def _validate_email(email: Optional[str]) -> str:
    if not email:
        raise ValueError("Email is required")
    parsed = parseaddr(email)[1]
    if not parsed or "@" not in parsed:
        raise ValueError("Invalid email address")
    return parsed.lower()


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
        return jsonify({"error": "Not authenticated"}), 401

    subscription = subscription_store.get_subscription(email)
    return jsonify(
        {
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

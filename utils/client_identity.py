"""
Cookie-backed client identifier helpers.
"""

from __future__ import annotations

import secrets

from flask import g, request

from config import (
    CLIENT_ID_COOKIE_MAX_AGE,
    CLIENT_ID_COOKIE_NAME,
    CLIENT_ID_TOKEN_BYTES,
)


def _generate_client_id() -> str:
    return secrets.token_urlsafe(CLIENT_ID_TOKEN_BYTES)


def get_client_id() -> str:
    """Return a stable identifier tied to the requesting browser."""
    cached = getattr(g, "client_id", None)
    if cached:
        return cached

    existing = request.cookies.get(CLIENT_ID_COOKIE_NAME)
    if existing:
        client_id = existing
        g.client_id_needs_cookie = False
    else:
        client_id = _generate_client_id()
        g.client_id_needs_cookie = True

    g.client_id = client_id
    return client_id


def ensure_client_id_cookie(response):
    """Set the client ID cookie for responses when a new identifier was generated."""
    if not getattr(g, "client_id_needs_cookie", False):
        return response
    client_id = getattr(g, "client_id", None)
    if not client_id:
        return response
    response.set_cookie(
        CLIENT_ID_COOKIE_NAME,
        client_id,
        httponly=True,
        secure=request.is_secure,
        samesite="Lax",
        max_age=CLIENT_ID_COOKIE_MAX_AGE,
        path="/",
    )
    return response

"""
Server-side helpers for issuing and validating captcha nonces/tokens.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Dict

from flask import Request

from config import SECRET_KEY

CAPTCHA_COOKIE_NAME = "captcha_token"


@dataclass
class CaptchaNonce:
    nonce: str
    client_ip: str
    issued_at: float
    verified: bool = False


_nonces: Dict[str, CaptchaNonce] = {}
_lock = threading.Lock()


def _now() -> float:
    return time.time()


def create_nonce(client_ip: str) -> str:
    """Generate and store a captcha nonce for the supplied client IP."""
    nonce = secrets.token_urlsafe(24)
    now = _now()
    with _lock:
        _nonces[nonce] = CaptchaNonce(nonce=nonce, client_ip=client_ip, issued_at=now)
    return nonce


def mark_verified(nonce: str, client_ip: str) -> bool:
    """
    Mark the nonce as verified if it exists, is not expired, and matches the client IP.
    """
    with _lock:
        meta = _nonces.get(nonce)
        if not meta:
            return False
        if meta.client_ip != client_ip:
            return False
        meta.verified = True
        # Once verified we no longer need to keep it around.
        _nonces.pop(nonce, None)
        return True


def _sign(nonce: str, timestamp: int) -> str:
    payload = f"{nonce}:{timestamp}".encode("utf-8")
    secret = SECRET_KEY.encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def generate_token(nonce: str, timestamp: int | None = None) -> str:
    if timestamp is None:
        timestamp = int(_now())
    signature = _sign(nonce, timestamp)
    return f"{nonce}.{timestamp}.{signature}"


def _parse_token(token: str):
    try:
        nonce, timestamp_str, signature = token.split(".")
        timestamp = int(timestamp_str)
        return nonce, timestamp, signature
    except (ValueError, TypeError):
        return None


def token_is_valid(token: str) -> bool:
    parsed = _parse_token(token)
    if not parsed:
        return False
    nonce, timestamp, signature = parsed
    expected_sig = _sign(nonce, timestamp)
    if not hmac.compare_digest(expected_sig, signature):
        return False
    return True


def is_verified(request: Request) -> bool:
    """Return True when the captcha token cookie validates."""
    token = request.cookies.get(CAPTCHA_COOKIE_NAME)
    if not token:
        return False
    return token_is_valid(token)

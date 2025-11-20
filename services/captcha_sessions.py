"""
Server-side helpers for issuing and validating captcha nonces/tokens.
"""

from __future__ import annotations

import hashlib
import hmac
import random
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
    client_id: str
    issued_at: float
    min_drag_distance: float
    min_duration_ms: int
    min_move_events: int


_nonces: Dict[str, CaptchaNonce] = {}
_lock = threading.Lock()

MIN_DRAG_DISTANCE_RANGE = (260.0, 420.0)
MIN_DURATION_RANGE = (1500, 2600)
MIN_MOVE_EVENTS_RANGE = (12, 24)


def _now() -> float:
    return time.time()


def create_nonce(client_id: str) -> str:
    """Generate and store a captcha nonce for the supplied client identifier."""
    nonce = secrets.token_urlsafe(24)
    now = _now()
    min_distance = random.uniform(*MIN_DRAG_DISTANCE_RANGE)
    min_duration = random.randint(*MIN_DURATION_RANGE)
    min_moves = random.randint(*MIN_MOVE_EVENTS_RANGE)
    with _lock:
        _nonces[nonce] = CaptchaNonce(
            nonce=nonce,
            client_id=client_id,
            issued_at=now,
            min_drag_distance=min_distance,
            min_duration_ms=min_duration,
            min_move_events=min_moves,
        )
    return nonce


def consume_nonce(nonce: str) -> CaptchaNonce | None:
    """Remove and return the nonce metadata for verification."""
    with _lock:
        return _nonces.pop(nonce, None)


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

"""
Lightweight in-memory rate limiter utilities for the Flask app.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Tuple


class RateLimiter:
    """Simple sliding-window rate limiter keyed by arbitrary identifiers."""

    def __init__(self) -> None:
        self._events: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> Tuple[bool, float | None]:
        """
        Check whether a request should be allowed.

        Returns a tuple of (allowed, retry_after_seconds). If allowed is False,
        retry_after_seconds indicates how long until the next request is permitted.
        """
        if limit <= 0 or window_seconds <= 0:
            return True, None

        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            events = self._events.setdefault(key, deque())

            while events and events[0] <= window_start:
                events.popleft()

            if len(events) >= limit:
                retry_after = events[0] + window_seconds - now
                return False, max(0.0, retry_after)

            events.append(now)
            return True, None

    def clear(self, key: str) -> None:
        """Remove all tracking data for a key."""
        with self._lock:
            self._events.pop(key, None)


rate_limiter = RateLimiter()


"""
Lightweight in-memory rate limiter utilities for the Flask app.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict, Tuple

# How often stale keys are swept, and a hard cap on tracked keys. Without this,
# every new client id (e.g. cookieless requests) leaves a key behind forever.
_SWEEP_INTERVAL_SECONDS = 60
_MAX_TRACKED_KEYS = 50000


class RateLimiter:
    """Simple sliding-window rate limiter keyed by arbitrary identifiers."""

    def __init__(self) -> None:
        self._events: Dict[str, Deque[float]] = {}
        self._windows: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._last_sweep = time.time()

    def _sweep_locked(self, now: float) -> None:
        """Drop keys whose newest event is older than their window. Caller holds the lock."""
        stale = [
            key
            for key, events in self._events.items()
            if not events or events[-1] <= now - self._windows.get(key, 0)
        ]
        for key in stale:
            self._events.pop(key, None)
            self._windows.pop(key, None)
        self._last_sweep = now

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
            if (
                now - self._last_sweep >= _SWEEP_INTERVAL_SECONDS
                or len(self._events) >= _MAX_TRACKED_KEYS
            ):
                self._sweep_locked(now)

            events = self._events.setdefault(key, deque())
            self._windows[key] = max(self._windows.get(key, 0), window_seconds)

            while events and events[0] <= window_start:
                events.popleft()

            if len(events) >= limit:
                retry_after = events[0] + window_seconds - now
                return False, max(0.0, retry_after)

            events.append(now)
            return True, None

    def refund(self, key: str) -> None:
        """Give back the most recent allowed event for a key (e.g. the action failed)."""
        with self._lock:
            events = self._events.get(key)
            if events:
                events.pop()

    def clear(self, key: str) -> None:
        """Remove all tracking data for a key."""
        with self._lock:
            self._events.pop(key, None)
            self._windows.pop(key, None)


rate_limiter = RateLimiter()

"""
Background scheduler responsible for dispatching daily monitoring reports.
"""

from __future__ import annotations

import atexit
import logging
from typing import Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
except ImportError:  # pragma: no cover - optional dependency
    BackgroundScheduler = None  # type: ignore
    CronTrigger = None  # type: ignore
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import DAILY_REPORT_SEND_HOUR, DAILY_REPORT_SEND_MINUTE, ENABLE_DAILY_REPORTS, TIMEZONE
from services import report_service

LOGGER = logging.getLogger(__name__)

_scheduler: Optional[BackgroundScheduler] = None


def _resolve_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        LOGGER.warning("Falling back to UTC timezone for scheduler; invalid TIMEZONE=%s", TIMEZONE)
        return ZoneInfo("UTC")


def start_scheduler() -> None:
    """Start the APScheduler background job if enabled."""
    global _scheduler
    if not ENABLE_DAILY_REPORTS:
        LOGGER.info("Daily report scheduler disabled via configuration")
        return

    if BackgroundScheduler is None or CronTrigger is None:
        LOGGER.warning("APScheduler is not available; daily report scheduler will not start")
        return

    if _scheduler and _scheduler.running:
        return

    timezone = _resolve_timezone()
    scheduler = BackgroundScheduler(timezone=timezone)
    trigger = CronTrigger(
        hour=DAILY_REPORT_SEND_HOUR,
        minute=DAILY_REPORT_SEND_MINUTE,
        timezone=timezone,
    )
    scheduler.add_job(report_service.run_daily_dispatch, trigger, name="daily-monitoring-report")
    scheduler.start()
    _scheduler = scheduler

    LOGGER.info("Daily report scheduler started (hour=%s, timezone=%s)", DAILY_REPORT_SEND_HOUR, timezone)

    atexit.register(lambda: shutdown(wait=False))


def shutdown(wait: bool = False) -> None:
    """Gracefully stop the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        LOGGER.info("Stopping daily report scheduler")
        _scheduler.shutdown(wait=wait)
    _scheduler = None

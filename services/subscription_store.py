"""
SQLite-backed storage for login tokens, sessions, and monitoring subscriptions.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

from config import (
    LOGIN_TOKEN_TTL_MINUTES,
    SESSION_TTL_DAYS,
    SUBSCRIPTION_DB_PATH,
)

_DB_LOCK = threading.RLock()
_PENDING_RECLAIM_GRACE = timedelta(minutes=30)


def _ensure_parent_directory() -> None:
    """Create the directory that will contain the SQLite database if needed."""
    db_path = Path(SUBSCRIPTION_DB_PATH)
    if not db_path.parent.exists():
        db_path.parent.mkdir(parents=True, exist_ok=True)


def _utcnow() -> datetime:
    """Return a naive UTC timestamp."""
    return datetime.utcnow()


def _connect() -> sqlite3.Connection:
    """Create a new SQLite connection."""
    connection = sqlite3.connect(
        SUBSCRIPTION_DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def _db_cursor() -> Iterable[sqlite3.Cursor]:
    """Context manager that yields a cursor with thread-safe access."""
    with _DB_LOCK:
        conn = _connect()
        try:
            cursor = conn.cursor()
            yield cursor
            conn.commit()
        finally:
            conn.close()


def initialize() -> None:
    """Initialize the SQLite database schema if it does not already exist."""
    _ensure_parent_directory()
    with _db_cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS login_tokens (
                token TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                used_at TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                email TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP
            )
            """
        )

        cursor.execute("PRAGMA table_info(sessions)")
        columns = cursor.fetchall()
        expires_col = None
        for col in columns:
            if col["name"] == "expires_at":
                expires_col = col
                break

        if expires_col is not None and expires_col["notnull"]:
            cursor.execute("ALTER TABLE sessions RENAME TO sessions_old")
            cursor.execute(
                """
                CREATE TABLE sessions (
                    token TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    expires_at TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                INSERT INTO sessions (token, email, created_at, expires_at)
                SELECT token, email, created_at, expires_at FROM sessions_old
                """
            )
            cursor.execute("DROP TABLE sessions_old")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                email TEXT PRIMARY KEY,
                settings TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dispatch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                report_date TEXT NOT NULL,
                status TEXT NOT NULL,
                claimed_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                error TEXT,
                UNIQUE(email, report_date)
            )
            """
        )


def store_login_token(email: str, token: str, expires_at: Optional[datetime] = None) -> None:
    """Persist a one-time login token."""
    email_normalized = email.strip().lower()
    now = _utcnow()
    expiry = expires_at or now + timedelta(minutes=LOGIN_TOKEN_TTL_MINUTES)
    with _db_cursor() as cursor:
        cursor.execute(
            """
            INSERT OR REPLACE INTO login_tokens (token, email, created_at, expires_at, used, used_at)
            VALUES (:token, :email, :created_at, :expires_at, 0, NULL)
            """,
            {
                "token": token,
                "email": email_normalized,
                "created_at": now,
                "expires_at": expiry,
            },
        )

def consume_login_token(token: str) -> Optional[str]:
    """Mark a login token as used and return the associated email."""
    now = _utcnow()
    with _db_cursor() as cursor:
        cursor.execute(
            """
            SELECT email, expires_at, used FROM login_tokens WHERE token = :token
            """,
            {"token": token},
        )
        row = cursor.fetchone()
        if not row:
            return None

        if row["used"]:
            return None

        expires_at = row["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        if expires_at < now:
            cursor.execute("DELETE FROM login_tokens WHERE token = :token", {"token": token})
            return None

        cursor.execute(
            """
            UPDATE login_tokens
            SET used = 1,
                used_at = :used_at
            WHERE token = :token
            """,
            {"token": token, "used_at": now},
        )
        return row["email"]


def create_session(email: str, ttl_days: Optional[int] = None) -> str:
    """Create a persistent session entry and return the session token."""
    import secrets

    session_token = secrets.token_urlsafe(32)
    now = _utcnow()
    ttl = ttl_days if ttl_days is not None else SESSION_TTL_DAYS
    expires_at = None
    if ttl is not None:
        expires_at = now + timedelta(days=ttl)

    with _db_cursor() as cursor:
        cursor.execute(
            """
            INSERT OR REPLACE INTO sessions (token, email, created_at, expires_at)
            VALUES (:token, :email, :created_at, :expires_at)
            """,
            {
                "token": session_token,
                "email": email.strip().lower(),
                "created_at": now,
                "expires_at": expires_at,
            },
        )

    return session_token


def get_session(token: str) -> Optional[Dict[str, Any]]:
    """Look up a session by token, returning None if missing or expired."""
    now = _utcnow()
    with _db_cursor() as cursor:
        cursor.execute(
            "SELECT token, email, created_at, expires_at FROM sessions WHERE token = :token",
            {"token": token},
        )
        row = cursor.fetchone()
        if not row:
            return None

        expires_at = row["expires_at"]
        if expires_at is not None:
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at)

            if expires_at < now:
                cursor.execute("DELETE FROM sessions WHERE token = :token", {"token": token})
                return None

        return {
            "token": row["token"],
            "email": row["email"],
            "created_at": row["created_at"],
            "expires_at": expires_at,
        }


def delete_session(token: str) -> None:
    """Remove a session token."""
    with _db_cursor() as cursor:
        cursor.execute("DELETE FROM sessions WHERE token = :token", {"token": token})


def upsert_subscription(email: str, settings: Dict[str, Any]) -> None:
    """Create or update a monitoring subscription for an email address."""
    now = _utcnow()
    settings_json = json.dumps(settings, separators=(",", ":"), sort_keys=True)
    with _db_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO subscriptions (email, settings, created_at, updated_at)
            VALUES (:email, :settings, :created_at, :created_at)
            ON CONFLICT(email) DO UPDATE SET
                settings = excluded.settings,
                updated_at = :updated_at
            """,
            {
                "email": email.strip().lower(),
                "settings": settings_json,
                "created_at": now,
                "updated_at": now,
            },
        )


def delete_subscription(email: str) -> None:
    """Remove an email subscription and associated sessions."""
    normalized = email.strip().lower()
    with _db_cursor() as cursor:
        cursor.execute("DELETE FROM subscriptions WHERE email = :email", {"email": normalized})
        cursor.execute("DELETE FROM sessions WHERE email = :email", {"email": normalized})


def get_subscription(email: str) -> Optional[Dict[str, Any]]:
    """Fetch subscription settings for an email, if present."""
    with _db_cursor() as cursor:
        cursor.execute(
            """
            SELECT email, settings, created_at, updated_at
            FROM subscriptions
            WHERE email = :email
            """,
            {"email": email.strip().lower()},
        )
        row = cursor.fetchone()
        if not row:
            return None

        settings = json.loads(row["settings"])
        return {
            "email": row["email"],
            "settings": settings,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def list_subscriptions() -> Iterable[Dict[str, Any]]:
    """Return all active subscriptions."""
    with _db_cursor() as cursor:
        cursor.execute(
            "SELECT email, settings, created_at, updated_at FROM subscriptions ORDER BY email"
        )
        rows = cursor.fetchall()

    for row in rows:
        yield {
            "email": row["email"],
            "settings": json.loads(row["settings"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def cleanup_expired_artifacts() -> None:
    """Delete expired login tokens and sessions."""
    now = _utcnow()
    with _db_cursor() as cursor:
        cursor.execute(
            "DELETE FROM login_tokens WHERE expires_at < :now OR used = 1",
            {"now": now},
        )
        cursor.execute(
            "DELETE FROM sessions WHERE expires_at < :now",
            {"now": now},
        )


def claim_daily_dispatch(email: str, report_date: Union[date, datetime, str]) -> Optional[int]:
    """
    Attempt to claim the daily dispatch for an email + report date combination.

    Returns the dispatch_log row ID that was claimed, or None if another worker
    already processed the same report.
    """
    normalized_email = email.strip().lower()
    if isinstance(report_date, datetime):
        date_key = report_date.date().isoformat()
    elif isinstance(report_date, date):
        date_key = report_date.isoformat()
    else:
        date_key = str(report_date).strip()
    if not date_key:
        raise ValueError("report_date must not be empty")

    claimed_at = _utcnow()
    with _db_cursor() as cursor:
        try:
            cursor.execute(
                """
                INSERT INTO dispatch_log (email, report_date, status, claimed_at)
                VALUES (:email, :report_date, 'pending', :claimed_at)
                """,
                {
                    "email": normalized_email,
                    "report_date": date_key,
                    "claimed_at": claimed_at,
                },
            )
            return int(cursor.lastrowid)
        except sqlite3.IntegrityError:
            cursor.execute(
                """
                SELECT id, status, claimed_at, completed_at
                WHERE email = :email AND report_date = :report_date
                """,
                {"email": normalized_email, "report_date": date_key},
            )
            row = cursor.fetchone()
            if not row:
                return None

            status = row["status"]
            completed_at = row["completed_at"]
            if status in {"sent", "skipped"}:
                return None

            if status == "pending" and not completed_at:
                existing_claimed = row["claimed_at"]
                existing_claimed_dt: Optional[datetime]
                if isinstance(existing_claimed, str):
                    try:
                        existing_claimed_dt = datetime.fromisoformat(existing_claimed)
                    except ValueError:
                        existing_claimed_dt = None
                else:
                    existing_claimed_dt = existing_claimed

                if existing_claimed_dt and (claimed_at - existing_claimed_dt) < _PENDING_RECLAIM_GRACE:
                    return None

            cursor.execute(
                """
                UPDATE dispatch_log
                SET status = 'pending',
                    claimed_at = :claimed_at,
                    completed_at = NULL,
                    error = NULL
                WHERE id = :id
                """,
                {"claimed_at": claimed_at, "id": row["id"]},
            )
            return int(row["id"])


def finalize_daily_dispatch(dispatch_id: Optional[int], status: str, error: Optional[str] = None) -> None:
    """Update the dispatch log entry with the final status and optional error detail."""
    if dispatch_id is None:
        return

    if status not in {"sent", "skipped", "failed"}:
        raise ValueError(f"Unknown dispatch status: {status}")

    completed_at = _utcnow()
    with _db_cursor() as cursor:
        cursor.execute(
            """
            UPDATE dispatch_log
            SET status = :status,
                completed_at = :completed_at,
                error = :error
            WHERE id = :id
            """,
            {
                "status": status,
                "completed_at": completed_at,
                "error": error,
                "id": dispatch_id,
            },
        )

"""
Admin utilities for inspecting the subscriptions database through a protected API.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import date, datetime
from typing import Any, Dict, List, Tuple

from flask import Blueprint, jsonify, request, session
from utils.client_identity import get_client_id

from config import SECRET_KEY, SUBSCRIPTION_DB_PATH
from services.rate_limiter import rate_limiter

admin_bp = Blueprint("admin", __name__)

ADMIN_LOGIN_LIMIT = 3
ADMIN_LOGIN_WINDOW_SECONDS = 24 * 60 * 60
ADMIN_SESSION_TTL_SECONDS = 60 * 60  # Require re-authentication after an hour
MAX_RESULT_ROWS = 500



def _check_secret_key() -> Tuple[bool, Any]:
    if not SECRET_KEY:
        return False, (
            jsonify({"error": "Admin console is not configured. SECRET_KEY must be set."}),
            500,
        )
    return True, None


def _require_admin_session() -> bool:
    if not session.get("admin_authenticated"):
        return False
    authenticated_at = session.get("admin_authenticated_at")
    if not authenticated_at:
        return False
    if (time.time() - authenticated_at) > ADMIN_SESSION_TTL_SECONDS:
        session.pop("admin_authenticated", None)
        session.pop("admin_authenticated_at", None)
        return False
    return True


def _ensure_admin_session():
    if _require_admin_session():
        return None
    return jsonify({"error": "admin_auth_required"}), 401


def _open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(
        SUBSCRIPTION_DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA query_only = ON")
    return conn


def _normalize_sql(sql: str) -> str:
    return (sql or "").strip()


def _validate_sql(sql: str) -> Tuple[bool, str | None]:
    normalized = _normalize_sql(sql)
    if not normalized:
        return False, "Query must not be empty."

    first_token = normalized.split(None, 1)[0].upper()
    if first_token in {"SELECT", "WITH", "PRAGMA"}:
        return True, None
    return False, "Only SELECT, WITH, or PRAGMA statements are allowed."


@admin_bp.route("/admin/login", methods=["POST"])
def admin_login():
    ok, error_response = _check_secret_key()
    if not ok:
        return error_response

    payload = request.get_json(silent=True) or {}
    password = str(payload.get("password") or "").strip()

    if not password:
        return jsonify({"error": "Password is required"}), 400

    client_id = get_client_id()
    key = f"admin-login:cid:{client_id}"
    allowed, retry_after = rate_limiter.allow(key, ADMIN_LOGIN_LIMIT, ADMIN_LOGIN_WINDOW_SECONDS)
    if not allowed:
        wait_seconds = max(1, int(retry_after or ADMIN_LOGIN_WINDOW_SECONDS))
        response = jsonify({"error": "Too many login attempts. Try again later."})
        response.headers["Retry-After"] = str(wait_seconds)
        return response, 429

    if password != SECRET_KEY:
        return jsonify({"error": "Invalid password"}), 401

    # Reset the limiter after a successful login so new attempts are available.
    rate_limiter.clear(key)
    session["admin_authenticated"] = True
    session["admin_authenticated_at"] = int(time.time())
    session.permanent = False

    return jsonify({"authenticated": True})


@admin_bp.route("/admin/tables", methods=["GET"])
def list_tables():
    guard = _ensure_admin_session()
    if guard:
        return guard

    with _open_db() as conn:
        cursor = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type IN ('table', 'view')
            ORDER BY name
            """
        )
        tables = [row["name"] for row in cursor.fetchall()]

    return jsonify({"tables": tables})


def _execute_read_query(sql: str) -> Tuple[List[str], List[Dict[str, Any]], bool]:
    with _open_db() as conn:
        cursor = conn.execute(sql)
        columns = [description[0] for description in cursor.description or []]
        raw_rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)
        truncated = len(raw_rows) > MAX_RESULT_ROWS
        limited_rows = raw_rows[:MAX_RESULT_ROWS]
        rows = [
            {col: _serialize_value(row[col]) for col in columns}
            for row in limited_rows
        ]
    return columns, rows, truncated


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    return value


@admin_bp.route("/admin/query", methods=["POST"])
def run_query():
    guard = _ensure_admin_session()
    if guard:
        return guard

    payload = request.get_json(silent=True) or {}
    sql = payload.get("sql", "")
    is_valid, error_message = _validate_sql(sql)
    if not is_valid:
        return jsonify({"error": error_message}), 400

    try:
        columns, rows, truncated = _execute_read_query(sql)
    except sqlite3.Error as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "columns": columns,
            "rows": rows,
            "truncated": truncated,
        }
    )

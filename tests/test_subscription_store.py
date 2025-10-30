import os
from datetime import datetime, timedelta

import pytest

from services import subscription_store


@pytest.fixture(autouse=True)
def isolated_subscription_db(tmp_path, monkeypatch):
  db_path = tmp_path / "subscriptions.db"
  monkeypatch.setattr(subscription_store, "SUBSCRIPTION_DB_PATH", str(db_path), raising=False)
  subscription_store.initialize()
  yield
  if db_path.exists():
    os.remove(db_path)


def test_login_token_and_session_roundtrip():
  email = "user@example.com"
  token = "test-token"

  subscription_store.store_login_token(email, token)
  assert subscription_store.consume_login_token(token) == email
  # Token cannot be reused
  assert subscription_store.consume_login_token(token) is None

  session_token = subscription_store.create_session(email, ttl_days=1)
  session = subscription_store.get_session(session_token)
  assert session is not None
  assert session["email"] == email

  subscription_store.delete_session(session_token)
  assert subscription_store.get_session(session_token) is None


def test_subscription_crud_and_cleanup():
  email = "alerts@example.com"
  settings = {
    "start_date": "2024-01-01",
    "end_date": "2024-01-31",
    "signal_ids": ["1001", "1002"],
    "pct_change_improvement": 0.1,
    "pct_change_degradation": 0.2,
  }

  subscription_store.upsert_subscription(email, settings)
  subscription = subscription_store.get_subscription(email)
  assert subscription is not None
  assert subscription["settings"] == settings

  subscriptions = list(subscription_store.list_subscriptions())
  assert len(subscriptions) == 1
  assert subscriptions[0]["email"] == email

  # Expired tokens are removed during cleanup
  expired = datetime.utcnow() - timedelta(minutes=5)
  subscription_store.store_login_token(email, "expired-token", expires_at=expired)
  subscription_store.cleanup_expired_artifacts()
  assert subscription_store.consume_login_token("expired-token") is None

  # delete_subscription removes subscription and sessions
  session_token = subscription_store.create_session(email, ttl_days=1)
  subscription_store.delete_subscription(email)
  assert subscription_store.get_subscription(email) is None
  assert subscription_store.get_session(session_token) is None

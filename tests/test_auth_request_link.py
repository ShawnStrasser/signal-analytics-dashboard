"""Login-link endpoint: a failed email send must not consume the rate-limit budget."""

from flask import Flask

from routes import api_auth
from routes.api_auth import auth_bp
from services.rate_limiter import RateLimiter


def _make_client(monkeypatch, send_impl):
    limiter = RateLimiter()
    monkeypatch.setattr(api_auth, "rate_limiter", limiter)
    monkeypatch.setattr(api_auth.subscription_store, "store_login_token", lambda e, t: None)
    monkeypatch.setattr(api_auth.email_service, "send_email", send_impl)
    app = Flask(__name__)
    app.register_blueprint(auth_bp, url_prefix="/api")
    return app.test_client()


def test_failed_send_returns_502_and_refunds_rate_limit(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("Failed to send email via Brevo: 401")

    client = _make_client(monkeypatch, boom)
    body = {"email": "someone@example.gov"}

    first = client.post("/api/auth/request-link", json=body)
    assert first.status_code == 502

    # Immediate retry is not blocked by the 1-per-minute per-email limit
    second = client.post("/api/auth/request-link", json=body)
    assert second.status_code == 502


def test_successful_send_still_rate_limited(monkeypatch):
    client = _make_client(monkeypatch, lambda *a, **k: {})
    body = {"email": "someone@example.gov"}

    assert client.post("/api/auth/request-link", json=body).status_code == 200
    assert client.post("/api/auth/request-link", json=body).status_code == 429

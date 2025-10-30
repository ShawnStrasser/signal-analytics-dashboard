"""
Brevo email helper utilities.
"""

from __future__ import annotations

import base64
from typing import Iterable, Optional

try:
    import brevo_python
    from brevo_python.rest import ApiException
except ImportError:  # pragma: no cover - optional dependency in tests
    brevo_python = None  # type: ignore

    class ApiException(Exception):  # type: ignore
        """Fallback ApiException when Brevo SDK is unavailable."""

from config import (
    BREVO_API_KEY,
    BREVO_DISABLE_SSL_VERIFY,
    EMAIL_SENDER_ADDRESS,
    EMAIL_SENDER_NAME,
)

_EMAIL_API: Optional["brevo_python.TransactionalEmailsApi"] = None


def _get_api() -> brevo_python.TransactionalEmailsApi:
    """Initialise or return the cached Brevo transactional email API client."""
    global _EMAIL_API
    if brevo_python is None:
        raise RuntimeError("brevo_python package is required to send email")

    if _EMAIL_API is not None:
        return _EMAIL_API

    if not BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY environment variable is not configured")

    configuration = brevo_python.Configuration()
    configuration.api_key["api-key"] = BREVO_API_KEY
    configuration.verify_ssl = not BREVO_DISABLE_SSL_VERIFY

    api_client = brevo_python.ApiClient(configuration)
    _EMAIL_API = brevo_python.TransactionalEmailsApi(api_client)
    return _EMAIL_API


def _attachment_payload(name: str, data: bytes) -> dict:
    """Convert raw bytes into a Brevo-compatible attachment."""
    encoded = base64.b64encode(data).decode("ascii")
    return {"name": name, "content": encoded}


def send_email(
    to_email: str,
    subject: str,
    html_content: str,
    *,
    attachments: Optional[Iterable[tuple[str, bytes]]] = None,
    reply_to: Optional[str] = None,
) -> dict:
    """
    Send an email using Brevo.

    Args:
        to_email: Recipient email address.
        subject: Email subject line.
        html_content: HTML body.
        attachments: Optional iterable of (filename, file_bytes).
        reply_to: Optional reply-to email address.

    Returns:
        Brevo API response dict.
    """
    api = _get_api()

    attachment_payload = []
    if attachments:
        for filename, content in attachments:
            attachment_payload.append(_attachment_payload(filename, content))

    message = brevo_python.SendSmtpEmail(
        to=[{"email": to_email}],
        sender={"email": EMAIL_SENDER_ADDRESS, "name": EMAIL_SENDER_NAME},
        subject=subject,
        html_content=html_content,
        attachment=attachment_payload if attachment_payload else None,
        reply_to={"email": reply_to} if reply_to else None,
    )

    try:
        return api.send_transac_email(message)
    except ApiException as exc:  # pragma: no cover - Brevo client raises ApiException
        raise RuntimeError(f"Failed to send email via Brevo: {exc}") from exc

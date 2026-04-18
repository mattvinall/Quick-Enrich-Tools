import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.services import email_service


@pytest.mark.asyncio
async def test_send_results_email_awaits_resend_call(monkeypatch):
    """The sync resend SDK must be executed via asyncio.to_thread so we actually wait for the send."""
    monkeypatch.setattr(email_service.settings, "resend_api_key", "re_test")

    send_mock = MagicMock(return_value={"id": "abc"})
    monkeypatch.setattr("app.services.email_service.resend.Emails.send", send_mock)

    await email_service.send_results_email(
        "test@example.com",
        "https://example.com/download/abc",
        {"total_rows": 10, "websites_found": 8, "contacts_enriched": 4},
    )

    send_mock.assert_called_once()


@pytest.mark.asyncio
async def test_send_results_email_raises_on_missing_recipient(monkeypatch):
    monkeypatch.setattr(email_service.settings, "resend_api_key", "re_test")
    send_mock = MagicMock()
    monkeypatch.setattr("app.services.email_service.resend.Emails.send", send_mock)

    await email_service.send_results_email("", "https://x", {"total_rows": 0})

    send_mock.assert_not_called()

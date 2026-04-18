"""Tests for /upload endpoint IP + email rate limiting.

Verifies that the upload router calls check_rate_limit for both the client IP
and the authenticated email on every request, and that submitting more than
settings.uploads_per_ip_per_day uploads from one IP returns HTTP 429.
"""
from __future__ import annotations

import io
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app import auth
from app.config import settings
from app.database import get_db
from app.main import app
from app.routers import upload as upload_router


def _make_token_payload() -> dict[str, str | int]:
    return {"sub": "rate-limit-test@example.com", "job_id": "pending"}


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """FastAPI test client with DB, auth, and pipeline dispatch stubbed out."""
    # Satisfy the lifespan JWT check without requiring a real env var.
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-do-not-use")

    # Stub out the DB dependency so upload_csv doesn't hit Postgres.
    fake_session = MagicMock()
    fake_session.add = MagicMock()
    fake_session.add_all = MagicMock()

    async def _flush() -> None:
        # Populate .id on staged objects the way Job/JobResult expect.
        call_args = fake_session.add.call_args_list
        for ca in call_args:
            obj = ca.args[0]
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    fake_session.flush = _flush
    fake_session.execute = AsyncMock()
    fake_session.commit = AsyncMock()
    fake_session.rollback = AsyncMock()
    fake_session.close = AsyncMock()

    async def _override_get_db():
        yield fake_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[auth.verify_token] = _make_token_payload

    # Don't actually kick off the pipeline during tests; just close the
    # coroutine so we don't leak RuntimeWarnings.
    def _fake_create_task(coro):
        coro.close()
        return MagicMock(add_done_callback=lambda *_: None)

    monkeypatch.setattr(upload_router.asyncio, "create_task", _fake_create_task)

    with TestClient(app) as tc:
        yield tc

    app.dependency_overrides.clear()


def _csv_bytes() -> bytes:
    return b"company,location\nAcme,NYC\n"


def _post_upload(client: TestClient) -> "httpx.Response":
    files = {"file": ("rows.csv", io.BytesIO(_csv_bytes()), "text/csv")}
    data = {
        "company_column": "company",
        "location_column": "location",
        "email_capture_id": str(uuid.uuid4()),
    }
    return client.post("/api/v1/upload", files=files, data=data)


def test_upload_calls_check_rate_limit_for_ip_and_email(client, monkeypatch):
    """The upload endpoint must rate-limit both the client IP and the email."""
    calls: list[tuple[str, str, str]] = []

    async def fake_check_rate_limit(db, identifier, identifier_type, action):
        calls.append((identifier, identifier_type, action))

    monkeypatch.setattr(upload_router, "check_rate_limit", fake_check_rate_limit)

    resp = _post_upload(client)
    assert resp.status_code == 200, resp.text

    # Both identifier types must be checked with action="upload".
    identifier_types = {c[1] for c in calls}
    assert identifier_types == {"ip", "email"}
    actions = {c[2] for c in calls}
    assert actions == {"upload"}

    # Email identifier must equal the subject from the verified token.
    email_calls = [c for c in calls if c[1] == "email"]
    assert email_calls[0][0] == "rate-limit-test@example.com"


def test_upload_returns_429_when_ip_limit_exceeded(client, monkeypatch):
    """Once check_rate_limit raises HTTP 429 for the IP, /upload must propagate it."""
    limit = settings.uploads_per_ip_per_day
    state = {"ip_count": 0, "email_count": 0}

    async def fake_check_rate_limit(db, identifier, identifier_type, action):
        if identifier_type == "ip":
            state["ip_count"] += 1
            if state["ip_count"] > limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded for ip. Try again later.",
                )
        else:
            state["email_count"] += 1

    monkeypatch.setattr(upload_router, "check_rate_limit", fake_check_rate_limit)

    # First `limit` requests should succeed.
    for i in range(limit):
        resp = _post_upload(client)
        assert resp.status_code == 200, f"request {i + 1}/{limit} failed: {resp.text}"

    # The (limit+1)th request must be rejected with 429.
    resp = _post_upload(client)
    assert resp.status_code == 429, resp.text
    assert "Rate limit exceeded" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_rate_limiter_knows_upload_action():
    """check_rate_limit must have a configured daily limit for action='upload'."""
    from app.services.rate_limiter import LIMITS

    assert ("ip", "upload") in LIMITS, "rate_limiter LIMITS missing ('ip', 'upload')"
    assert ("email", "upload") in LIMITS, "rate_limiter LIMITS missing ('email', 'upload')"
    assert LIMITS[("ip", "upload")] == settings.uploads_per_ip_per_day
    assert LIMITS[("email", "upload")] == settings.uploads_per_email_per_day

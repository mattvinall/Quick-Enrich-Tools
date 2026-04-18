"""When a background pipeline task raises, the Job must be marked failed."""
import uuid
from unittest.mock import AsyncMock

import pytest

from app.models import Job
from app.routers.maps import _mark_job_failed_on_error as maps_mark
from app.routers.funding import _mark_job_failed_on_error as funding_mark


@pytest.mark.asyncio
async def test_maps_mark_job_failed_sets_status(monkeypatch):
    captured: dict[str, object] = {}

    class FakeJob:
        status = "pending"
        error_message: str | None = None

    class FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def execute(self, q):
            r = AsyncMock(); r.scalar_one = lambda: captured["job"]; return r
        async def commit(self):
            captured["committed"] = True

    captured["job"] = FakeJob()
    monkeypatch.setattr("app.routers.maps.AsyncSessionLocal", lambda: FakeSession())

    await maps_mark(uuid.uuid4(), RuntimeError("boom"))

    assert captured["job"].status == "failed"
    assert "boom" in (captured["job"].error_message or "")
    assert captured.get("committed") is True


@pytest.mark.asyncio
async def test_funding_mark_job_failed_sets_status(monkeypatch):
    captured: dict[str, object] = {}

    class FakeJob:
        status = "pending"
        error_message: str | None = None

    class FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def execute(self, q):
            r = AsyncMock(); r.scalar_one = lambda: captured["job"]; return r
        async def commit(self):
            captured["committed"] = True

    captured["job"] = FakeJob()
    monkeypatch.setattr("app.routers.funding.AsyncSessionLocal", lambda: FakeSession())

    await funding_mark(uuid.uuid4(), RuntimeError("crash"))

    assert captured["job"].status == "failed"
    assert "crash" in (captured["job"].error_message or "")

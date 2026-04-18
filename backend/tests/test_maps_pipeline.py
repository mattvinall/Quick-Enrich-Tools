"""Maps pipeline should not fail the whole job when some searches yield 0 places."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers import maps_pipeline


@pytest.mark.asyncio
async def test_zero_total_places_fails_job(monkeypatch):
    """If *every* search returned nothing, the job is legitimately empty → failed."""
    calls: list[str] = []

    class FakeJob:
        id = uuid.uuid4()
        status = "pending"
        config = {"searches": [{"search_term": "x", "location": "y"}], "max_per_search": 20}
        started_at = None
        error_message = None
        total_rows = 0

    class FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def execute(self, q):
            r = MagicMock(); r.scalar_one = lambda: fake_job; return r
        async def commit(self): calls.append("commit")
        async def flush(self): calls.append("flush")
        def add_all(self, items): calls.append(f"add_all:{len(items)}")

    fake_job = FakeJob()

    async def zero_places(*args, **kwargs):
        return []

    monkeypatch.setattr(maps_pipeline, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(maps_pipeline, "batch_search_maps", zero_places)
    monkeypatch.setattr(maps_pipeline, "run_intel_pipeline", AsyncMock())
    monkeypatch.setattr(maps_pipeline, "update_job_progress", AsyncMock())

    await maps_pipeline.run_maps_pipeline({}, str(fake_job.id))

    assert fake_job.status == "failed"
    assert fake_job.error_message is not None


@pytest.mark.asyncio
async def test_partial_zero_hits_still_proceeds(monkeypatch):
    """If 2 of 3 searches hit but 1 was empty, we still run downstream phases."""
    intel_called: dict[str, bool] = {"run": False}

    class FakeJob:
        id = uuid.uuid4()
        status = "pending"
        config = {
            "searches": [
                {"search_term": "a", "location": "x"},
                {"search_term": "b", "location": "x"},
                {"search_term": "c", "location": "x"},
            ],
            "max_per_search": 20,
        }
        started_at = None
        error_message = None
        total_rows = 0

    class FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def execute(self, q):
            r = MagicMock(); r.scalar_one = lambda: fake_job; return r
        async def commit(self): pass
        async def flush(self): pass
        def add_all(self, items): pass

    fake_job = FakeJob()

    # Only one search yielded a place; two yielded none. Pipeline must proceed.
    async def mixed_places(*args, **kwargs):
        return [{
            "title": "Alpha", "website": "alpha.com",
            "search_term": "a", "location": "x",
        }]

    async def fake_intel(ctx, job_id):
        intel_called["run"] = True

    monkeypatch.setattr(maps_pipeline, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(maps_pipeline, "batch_search_maps", mixed_places)
    monkeypatch.setattr(maps_pipeline, "run_intel_pipeline", fake_intel)
    monkeypatch.setattr(maps_pipeline, "update_job_progress", AsyncMock())

    await maps_pipeline.run_maps_pipeline({}, str(fake_job.id))

    assert intel_called["run"] is True, "intel pipeline must still run when at least one place was found"
    assert fake_job.status != "failed"

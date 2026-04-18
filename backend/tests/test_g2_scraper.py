"""Tests for g2_scraper Serper fallback parallelization."""
import asyncio

import httpx
import pytest

from app.services import g2_scraper


@pytest.mark.asyncio
async def test_discover_g2_category_fires_serper_queries_in_parallel(monkeypatch):
    """All Serper queries must fire concurrently; total elapsed ~= 1x slowest query, not N* sequential."""

    call_count = {"n": 0}

    async def fake_post(self, *args, **kwargs):
        call_count["n"] += 1
        await asyncio.sleep(0.2)  # Simulate 200ms Serper latency

        class _Resp:
            status_code = 200

            def json(self):
                return {"organic": []}

            def raise_for_status(self):
                pass

        return _Resp()

    # Patch httpx.AsyncClient.post so every Serper call is a 200ms no-op.
    monkeypatch.setattr("app.services.g2_scraper.httpx.AsyncClient.post", fake_post)
    # Bypass caching (Redis unavailable in tests is fine — the code handles it).
    monkeypatch.setattr(g2_scraper.settings, "serper_api_key", "test")

    # Also bypass retry_async wrapper's delay — we want a single call per query.
    async def fake_retry_async(fn, *a, **kw):
        return await fn()

    monkeypatch.setattr(g2_scraper, "retry_async", fake_retry_async)

    start = asyncio.get_event_loop().time()
    async with httpx.AsyncClient() as client:
        await g2_scraper.discover_g2_category(
            client, "crm-software", "CRM", max_products=100
        )
    elapsed = asyncio.get_event_loop().time() - start

    # With 6 queries x 200ms sequential = 1.2s. Parallel should be ~200-400ms even
    # under load. Use a conservative ceiling that still distinguishes parallel from
    # sequential by a wide margin.
    assert elapsed < 0.6, f"Serper queries appear to run sequentially ({elapsed:.2f}s elapsed)"
    assert call_count["n"] >= 2

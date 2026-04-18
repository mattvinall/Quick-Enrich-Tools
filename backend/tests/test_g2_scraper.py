"""Tests for g2_scraper Serper fallback parallelization."""
import asyncio

import httpx
import pytest

from app.services import g2_scraper


@pytest.mark.asyncio
async def test_discover_g2_category_fires_serper_queries_in_parallel(monkeypatch):
    """All Serper queries must be in-flight at the same moment, not issued one-at-a-time."""

    in_flight = 0
    max_in_flight = 0
    call_count = 0

    async def fake_post(self, *args, **kwargs):
        nonlocal in_flight, max_in_flight, call_count
        call_count += 1
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        try:
            await asyncio.sleep(0.05)  # yield so sibling tasks can enter

            class _Resp:
                status_code = 200

                def json(self):
                    return {"organic": []}

                def raise_for_status(self):
                    pass

            return _Resp()
        finally:
            in_flight -= 1

    monkeypatch.setattr("app.services.g2_scraper.httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr(g2_scraper.settings, "serper_api_key", "test")

    async def fake_retry_async(fn, *a, **kw):
        return await fn()

    monkeypatch.setattr(g2_scraper, "retry_async", fake_retry_async)

    async with httpx.AsyncClient() as client:
        await g2_scraper.discover_g2_category(
            client, "crm-software", "CRM", max_products=100
        )

    # Sequential execution would produce max_in_flight == 1. Parallel execution must
    # have at least 2 queries overlapping.
    assert call_count >= 2
    assert max_in_flight >= 2, (
        f"Serper queries appear sequential: max concurrent in-flight = {max_in_flight}"
    )

"""Tests that Serper calls request the max page size and paginate Maps + news."""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services.serper import batch_search_maps, search_company


@pytest.mark.asyncio
async def test_search_company_requests_num_100(monkeypatch):
    """search_company should send num=100 to Serper so we see all candidate domains."""
    captured_payloads: list[dict] = []

    async def fake_post(self, url, **kwargs):
        captured_payloads.append(kwargs.get("json", {}))
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"organic": []})
        return resp

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr("app.services.serper.cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr("app.services.serper.cache_set", AsyncMock(return_value=None))

    async with httpx.AsyncClient() as client:
        await search_company(client, "Acme", "London", api_key="test")

    assert captured_payloads, "expected at least one Serper call"
    assert captured_payloads[0]["num"] == 100


@pytest.mark.asyncio
async def test_batch_search_maps_paginates_and_yields_more_than_one_page(monkeypatch):
    """batch_search_maps should paginate past 20 places and hit Serper with page>=2."""
    call_pages: list[int] = []

    async def fake_search_maps(client, query, location="", api_key=None, page=1):
        call_pages.append(page)
        if page == 1:
            places = [{"title": f"Biz{i}", "website": f"biz{i}.com"} for i in range(20)]
        elif page == 2:
            places = [{"title": f"Biz{i+20}", "website": f"biz{i+20}.com"} for i in range(20)]
        else:
            places = []
        return {"query": query, "places": places}

    monkeypatch.setattr("app.services.serper.search_maps", fake_search_maps)

    result = await batch_search_maps(
        [{"search_term": "coffee", "location": "Austin"}],
        max_per_search=40,
    )

    assert 2 in call_pages, f"expected to call page 2, got pages: {call_pages}"
    assert len(result) >= 30, f"expected >=30 deduped places across 2 pages, got {len(result)}"


@pytest.mark.asyncio
async def test_batch_search_maps_stops_at_max_per_search(monkeypatch):
    """Pagination must stop once we have max_per_search results for that term."""
    call_pages: list[int] = []

    async def fake_search_maps(client, query, location="", api_key=None, page=1):
        call_pages.append(page)
        return {
            "query": query,
            "places": [
                {"title": f"Biz-{page}-{i}", "website": f"biz-{page}-{i}.com"}
                for i in range(20)
            ],
        }

    monkeypatch.setattr("app.services.serper.search_maps", fake_search_maps)

    result = await batch_search_maps(
        [{"search_term": "coffee", "location": "Austin"}],
        max_per_search=25,
    )

    assert len(result) >= 20, "expected at least 20 results from first page"
    assert 3 not in call_pages, f"should not have called page 3 (max 25 hit on page 2), got {call_pages}"

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
async def test_batch_search_maps_expands_to_nearby_cities(monkeypatch):
    """batch_search_maps should fan out to nearby cities parsed from seed addresses
    and return more than the 20-per-call Serper cap."""
    call_locations: list[str] = []

    async def fake_search_maps(client, query, location="", api_key=None, page=1):
        call_locations.append(location)
        if location == "Austin, TX":
            # Seed page: 20 places whose addresses point at nearby Austin-area cities
            cities = ["Round Rock", "Cedar Park", "Pflugerville"]
            places = [
                {
                    "title": f"Biz{i}",
                    "placeId": f"seed-{i}",
                    "website": f"biz{i}.com",
                    "address": f"{100+i} Main St, {cities[i % len(cities)]}, TX 78701",
                }
                for i in range(20)
            ]
        else:
            # Expansion call: return a fresh set of 20 places unique to this city
            places = [
                {
                    "title": f"{location}-Biz{i}",
                    "placeId": f"{location}-{i}",
                    "website": f"{location.lower().replace(' ', '')}-biz{i}.com",
                    "address": f"{i} Elm St, {location} 78664",
                }
                for i in range(20)
            ]
        return {"query": query, "places": places}

    monkeypatch.setattr("app.services.serper.search_maps", fake_search_maps)

    result = await batch_search_maps(
        [{"search_term": "coffee", "location": "Austin, TX"}],
        max_per_search=100,
    )

    # First call is the seed, subsequent calls are the fan-out cities
    assert call_locations[0] == "Austin, TX"
    nearby_calls = [loc for loc in call_locations[1:] if loc]
    assert nearby_calls, f"expected fan-out calls after seed, got: {call_locations}"
    # Should have called at least two different nearby cities (parsed from seed addresses)
    assert len(set(nearby_calls)) >= 2, (
        f"expected fan-out to multiple nearby cities, got: {nearby_calls}"
    )
    # Final result should exceed a single call's 20 cap
    assert len(result) > 20, f"expected >20 deduped places after fan-out, got {len(result)}"


@pytest.mark.asyncio
async def test_batch_search_maps_stops_at_max_per_search(monkeypatch):
    """Fan-out must stop once max_per_search is reached."""
    call_locations: list[str] = []

    async def fake_search_maps(client, query, location="", api_key=None, page=1):
        call_locations.append(location)
        if location == "Austin, TX":
            places = [
                {
                    "title": f"Seed{i}",
                    "placeId": f"seed-{i}",
                    "address": f"{i} Main St, Round Rock, TX 78664",
                }
                for i in range(20)
            ]
        else:
            places = [
                {
                    "title": f"{location}-{i}",
                    "placeId": f"{location}-{i}",
                    "address": f"{i} Oak, {location} 78664",
                }
                for i in range(20)
            ]
        return {"query": query, "places": places}

    monkeypatch.setattr("app.services.serper.search_maps", fake_search_maps)

    result = await batch_search_maps(
        [{"search_term": "coffee", "location": "Austin, TX"}],
        max_per_search=25,
    )

    # We got at least the 20 seed results; fan-out fired to fill to 25
    assert 20 <= len(result) <= 25, f"expected 20-25 results with cap=25, got {len(result)}"

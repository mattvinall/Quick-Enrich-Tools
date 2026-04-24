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
async def test_batch_search_maps_expands_via_latlng_tiles(monkeypatch):
    """batch_search_maps should fan out via lat/lng tiles and return more than
    the 20-per-call Serper cap — using only lat/lng fields (no address parsing)
    so the behavior is country-agnostic."""
    calls: list[tuple[str, str | None]] = []  # (location, ll)

    def _seed_places():
        # 20 seed places scattered across ~5km around Austin downtown.
        # Addresses are in a non-US format to prove the fan-out doesn't depend
        # on address parsing (which a prior US-only regex version did).
        return [
            {
                "title": f"Seed{i}",
                "placeId": f"seed-{i}",
                "latitude": 30.2672 + (i - 10) * 0.003,
                "longitude": -97.7431 + (i - 10) * 0.003,
                "address": f"{i} Rua Principal, Austin district, no country",
            }
            for i in range(20)
        ]

    async def fake_search_maps(client, query, location="", ll=None, api_key=None, page=1):
        calls.append((location, ll))
        if ll is None:
            # Seed call anchored by text location
            return {"query": query, "places": _seed_places()}
        # Tile call — return 20 fresh places unique to this ll
        return {
            "query": query,
            "places": [
                {
                    "title": f"{ll}-Biz{i}",
                    "placeId": f"{ll}-{i}",
                    "latitude": 30.27 + i * 0.0001,
                    "longitude": -97.74 + i * 0.0001,
                    "address": f"{i} somewhere",
                }
                for i in range(20)
            ],
        }

    monkeypatch.setattr("app.services.serper.search_maps", fake_search_maps)

    result = await batch_search_maps(
        [{"search_term": "coffee", "location": "Austin, TX"}],
        max_per_search=100,
    )

    # First call is the text-location seed (no ll)
    assert calls[0] == ("Austin, TX", None)
    # Subsequent calls should all use ll (the fan-out tiles)
    tile_lls = [ll for (_loc, ll) in calls[1:] if ll is not None]
    assert tile_lls, f"expected lat/lng fan-out after seed, got: {calls}"
    # Multiple distinct tiles
    assert len(set(tile_lls)) >= 2, f"expected multiple distinct tiles, got: {tile_lls}"
    # Every tile should be a proper @lat,lng,zoom string
    for ll in tile_lls:
        assert ll.startswith("@") and ll.endswith("z") and ll.count(",") == 2, (
            f"malformed ll: {ll}"
        )
    # Final result should exceed a single call's 20 cap
    assert len(result) > 20, f"expected >20 deduped places after fan-out, got {len(result)}"


@pytest.mark.asyncio
async def test_batch_search_maps_stops_at_max_per_search(monkeypatch):
    """Fan-out must stop once max_per_search is reached."""
    call_count = [0]

    async def fake_search_maps(client, query, location="", ll=None, api_key=None, page=1):
        call_count[0] += 1
        if ll is None:
            return {
                "query": query,
                "places": [
                    {
                        "title": f"Seed{i}",
                        "placeId": f"seed-{i}",
                        "latitude": 30.27 + i * 0.01,
                        "longitude": -97.74 + i * 0.01,
                    }
                    for i in range(20)
                ],
            }
        return {
            "query": query,
            "places": [
                {
                    "title": f"{ll}-{i}",
                    "placeId": f"{ll}-{i}",
                    "latitude": 30.27,
                    "longitude": -97.74,
                }
                for i in range(20)
            ],
        }

    monkeypatch.setattr("app.services.serper.search_maps", fake_search_maps)

    result = await batch_search_maps(
        [{"search_term": "coffee", "location": "Austin, TX"}],
        max_per_search=25,
    )

    assert 20 <= len(result) <= 25, f"expected 20-25 results with cap=25, got {len(result)}"


@pytest.mark.asyncio
async def test_batch_search_maps_tiles_respect_radius_cap(monkeypatch):
    """Tiles should not drift beyond maps_expansion_max_radius_km from the seed
    centroid, even if the seed includes a far-away outlier."""
    from app.services.serper import _tile_centers_from_seed

    # Seed with a tight Miami cluster plus one outlier 300km north (near Orlando).
    # The cluster centroid should dominate; outlier-chasing should be clamped.
    seed = [
        {"latitude": 25.77, "longitude": -80.19},
        {"latitude": 25.80, "longitude": -80.21},
        {"latitude": 25.74, "longitude": -80.17},
        {"latitude": 25.79, "longitude": -80.13},
        {"latitude": 28.54, "longitude": -81.38},  # Orlando — 300km away
    ]
    tiles = _tile_centers_from_seed(seed, max_tiles=6, max_radius_km=50.0)
    centroid_lat = sum(s["latitude"] for s in seed) / len(seed)
    centroid_lng = sum(s["longitude"] for s in seed) / len(seed)
    # Every tile should be within ~50km of the centroid
    for lat, lng in tiles:
        dlat_km = abs(lat - centroid_lat) * 111.0
        # Longitude scales with cosine of centroid's latitude
        import math
        dlng_km = abs(lng - centroid_lng) * 111.0 * math.cos(math.radians(centroid_lat))
        dist_km = math.hypot(dlat_km, dlng_km)
        assert dist_km <= 75.0, (  # some slack for grid corners + pad
            f"tile ({lat}, {lng}) is {dist_km:.1f}km from centroid; exceeded radius cap"
        )

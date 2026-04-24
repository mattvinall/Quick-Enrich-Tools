import asyncio
import logging
import math
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.retry import retry_async

logger = logging.getLogger(__name__)


_EARTH_KM_PER_LAT_DEG = 111.0  # 1° latitude ≈ 111 km globally (varies 110.6–111.7)


def _tile_centers_from_seed(
    places: list[dict[str, object]],
    max_tiles: int,
    max_radius_km: float,
) -> list[tuple[float, float]]:
    """Compute lat/lng tile centers to fan out around a seed Maps result set.

    Uses only latitude/longitude (fields Serper /maps returns on every place),
    so this works for any country — no address-parsing, no US-only assumptions.

    The seed's bounding box is padded ~30% then clamped so no tile can drift
    farther than max_radius_km from the seed centroid. This prevents stray
    outlier places in the seed (or genuinely huge user inputs like a state
    name) from pulling results in from far-away regions. Longitude scaling
    uses cos(latitude) so the radius stays roughly isotropic near the poles.

    Returns [] when the seed has no usable coords — callers fall back to
    single-call behavior.
    """
    coords: list[tuple[float, float]] = []
    for p in places:
        lat = p.get("latitude")
        lng = p.get("longitude")
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            coords.append((float(lat), float(lng)))

    if len(coords) < 2 or max_tiles < 1:
        return []

    # Centroid of seed places; tiles can't drift beyond max_radius_km of this.
    centroid_lat = sum(c[0] for c in coords) / len(coords)
    centroid_lng = sum(c[1] for c in coords) / len(coords)

    # Convert max radius to degrees. Longitude-per-km shrinks with |latitude|;
    # floor cos() at 0.1 so we don't divide by ~0 near the poles.
    max_lat_delta = max_radius_km / _EARTH_KM_PER_LAT_DEG
    max_lng_delta = max_radius_km / (
        _EARTH_KM_PER_LAT_DEG * max(0.1, math.cos(math.radians(centroid_lat)))
    )

    lats = [c[0] for c in coords]
    lngs = [c[1] for c in coords]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)

    # Pad ~30% to reach adjacent neighborhoods.
    lat_pad = max(0.02, (max_lat - min_lat) * 0.15)
    lng_pad = max(0.02, (max_lng - min_lng) * 0.15)
    min_lat -= lat_pad
    max_lat += lat_pad
    min_lng -= lng_pad
    max_lng += lng_pad

    # Clamp the padded box to the radius cap around the centroid.
    min_lat = max(min_lat, centroid_lat - max_lat_delta)
    max_lat = min(max_lat, centroid_lat + max_lat_delta)
    min_lng = max(min_lng, centroid_lng - max_lng_delta)
    max_lng = min(max_lng, centroid_lng + max_lng_delta)

    # Square-ish grid sized to fit the tile budget (6 → 2×3, 9 → 3×3, 4 → 2×2).
    rows = max(1, math.isqrt(max_tiles))
    cols = rows if rows * rows >= max_tiles else rows + 1
    lat_denom = max(1, rows - 1)
    lng_denom = max(1, cols - 1)

    tiles: list[tuple[float, float]] = []
    for i in range(rows):
        for j in range(cols):
            lat = (min_lat + (max_lat - min_lat) * (i / lat_denom)
                   if lat_denom > 0 else (min_lat + max_lat) / 2)
            lng = (min_lng + (max_lng - min_lng) * (j / lng_denom)
                   if lng_denom > 0 else (min_lng + max_lng) / 2)
            tiles.append((lat, lng))
            if len(tiles) >= max_tiles:
                return tiles
    return tiles


def _format_ll(lat: float, lng: float, zoom: int = 12) -> str:
    """Format a lat/lng as Serper's `ll` param: '@lat,lng,zoom'."""
    return f"@{lat:.6f},{lng:.6f},{zoom}z"


def _parse_domain(url: str) -> str:
    """Extract the netloc from a URL, stripping the www. prefix."""
    try:
        netloc = urlparse(url).netloc
        return netloc.removeprefix("www.")
    except Exception:
        return ""


async def search_company(
    client: httpx.AsyncClient,
    company_name: str,
    location: str = "",
    api_key: str | None = None,
) -> dict[str, object]:
    """Search for a company's website via the Serper API.

    Requests num=100 so we see the long tail of candidate domains; the
    candidate_domain we return is still the top result.
    """
    cache_key = make_cache_key("serper", company_name.lower(), location.lower())
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("SERPER CACHE HIT: %s (%s)", company_name, location)
        return cached

    query_parts = [f'"{company_name}"']
    if location:
        query_parts.append(location)
    query_parts.append("official website")
    query = " ".join(query_parts)
    logger.info("SERPER SEARCH: %s", query)

    response = await client.post(
        "https://google.serper.dev/search",
        headers={
            "X-API-KEY": api_key or settings.serper_api_key,
            "Content-Type": "application/json",
        },
        json={"q": query, "num": 100},
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()

    organic: list[dict[str, object]] = data.get("organic", [])
    results: list[dict[str, object]] = []
    for item in organic:
        link: str = item.get("link", "")
        results.append(
            {
                "title": item.get("title", ""),
                "link": link,
                "snippet": item.get("snippet", ""),
                "domain": _parse_domain(link),
            }
        )

    candidate_domain: str = results[0]["domain"] if results else ""

    payload: dict[str, object] = {
        "query": query,
        "results": results,
        "candidate_domain": candidate_domain,
    }
    await cache_set(cache_key, payload, settings.cache_ttl_days)
    return payload


async def batch_search(
    rows: list[dict[str, object]],
    concurrency: int | None = None,
    api_key: str | None = None,
) -> list[dict[str, object]]:
    """Search each unique company_name/location pair once and map results back.

    Returns a list of dicts with keys: row_index, search_results, candidate_domain.
    """
    limit = concurrency if concurrency is not None else settings.serper_concurrency
    semaphore = asyncio.Semaphore(limit)

    # Group row indices by their dedup key (lowercased company_name|location).
    groups: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        company_name: str = str(row.get("company_name", ""))
        location: str = str(row.get("location", ""))
        dedup_key = f"{company_name.lower()}|{location.lower()}"
        groups.setdefault(dedup_key, []).append(idx)

    unique_keys = list(groups.keys())

    async with httpx.AsyncClient() as client:

        async def _search_one(dedup_key: str) -> tuple[str, dict[str, object] | BaseException]:
            company_name, _, location = dedup_key.partition("|")
            async with semaphore:
                try:
                    result = await retry_async(
                        lambda cn=company_name, loc=location: search_company(client, cn, loc, api_key=api_key),
                        max_retries=3,
                        base_delay=1.0,
                    )
                    return dedup_key, result
                except Exception as exc:
                    return dedup_key, exc

        raw_outcomes = await asyncio.gather(
            *[_search_one(key) for key in unique_keys],
            return_exceptions=True,
        )

    # Build a lookup from dedup_key -> search result (or None on error).
    key_to_result: dict[str, dict[str, object] | None] = {}
    for outcome in raw_outcomes:
        if isinstance(outcome, BaseException):
            logger.warning("batch_search error: %s", outcome)
            continue
        dedup_key, value = outcome
        if isinstance(value, BaseException):
            logger.warning("Serper search failed for '%s': %s", dedup_key, value)
            key_to_result[dedup_key] = None
        else:
            key_to_result[dedup_key] = value

    # Map results back to every original row index.
    output: list[dict[str, object]] = []
    for dedup_key, indices in groups.items():
        search_results = key_to_result.get(dedup_key)
        candidate_domain: str = (
            str(search_results["candidate_domain"]) if search_results else ""
        )
        for idx in indices:
            output.append(
                {
                    "row_index": idx,
                    "search_results": search_results,
                    "candidate_domain": candidate_domain,
                }
            )

    output.sort(key=lambda item: int(item["row_index"]))
    return output


async def search_maps(
    client: httpx.AsyncClient,
    query: str,
    location: str = "",
    ll: str | None = None,
    api_key: str | None = None,
    page: int = 1,
) -> dict[str, object]:
    """Search Google Maps via the Serper /maps endpoint for a single page.

    Either `location` (text) or `ll` (an '@lat,lng,zoom' string) anchors the
    geographic area. When `ll` is provided we omit the 'in {location}' suffix
    from the query so Google treats `ll` as the authority on WHERE to search.

    Returns a dict with keys: query, places (list of place dicts), page.
    Results are cached by query + location + ll + page for 3 days.
    """
    if ll:
        search_query = query
    else:
        search_query = f"{query} in {location}" if location else query
    cache_key = make_cache_key(
        "serper_maps", search_query.lower(), ll or "", f"p{page}"
    )
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info(
            "SERPER MAPS CACHE HIT: %s ll=%s page=%d",
            search_query, ll or "-", page,
        )
        return cached

    logger.info(
        "SERPER MAPS SEARCH: %s ll=%s page=%d",
        search_query, ll or "-", page,
    )

    body: dict[str, object] = {"q": search_query, "hl": "en"}
    if ll:
        body["ll"] = ll
    if page > 1:
        body["page"] = page

    response = await client.post(
        "https://google.serper.dev/maps",
        headers={
            "X-API-KEY": api_key or settings.serper_api_key,
            "Content-Type": "application/json",
        },
        json=body,
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()

    places: list[dict[str, object]] = data.get("places", [])
    payload: dict[str, object] = {"query": search_query, "places": places, "page": page}
    await cache_set(cache_key, payload, 3)
    return payload


async def batch_search_maps(
    searches: list[dict[str, str]],
    max_per_search: int | None = None,
    concurrency: int | None = None,
    api_key: str | None = None,
) -> list[dict[str, object]]:
    """Search Google Maps for multiple query+location pairs, paginating each.

    Each search: {"search_term": str, "location": str}
    Returns a flat list of place dicts, each augmented with 'search_term' and
    'location' keys. Deduplicates by normalized domain (then name+location).

    Paginates each search up to settings.maps_max_pages_per_search pages
    (Serper /maps returns ~20 per page) and stops early once the per-search
    cap is hit or a page returns zero new results.
    """
    limit = concurrency if concurrency is not None else settings.serper_concurrency
    per_search_cap = max_per_search if max_per_search is not None else settings.maps_max_per_search
    semaphore = asyncio.Semaphore(limit)
    expand = settings.maps_expand_nearby
    expansion_cap = settings.maps_expansion_max_tiles
    expansion_radius_km = settings.maps_expansion_max_radius_km

    async with httpx.AsyncClient() as client:

        async def _call_maps(
            term: str,
            location_str: str = "",
            ll: str | None = None,
        ) -> list[dict[str, object]]:
            """Single /maps call with retry + semaphore. Returns [] on failure."""
            async with semaphore:
                try:
                    result = await retry_async(
                        lambda l=location_str, coord=ll: search_maps(
                            client, term, l, ll=coord, api_key=api_key, page=1,
                        ),
                        max_retries=3,
                        base_delay=1.0,
                    )
                    return result.get("places") or []
                except Exception as exc:
                    logger.warning(
                        "Maps search failed for '%s' loc='%s' ll=%s: %s",
                        term, location_str, ll or "-", exc,
                    )
                    return []

        async def _search_one(
            search: dict[str, str],
        ) -> tuple[str, str, list[dict[str, object]]]:
            term = search["search_term"]
            loc = search["location"]
            collected: list[dict[str, object]] = []
            seen_ids: set[str] = set()

            def _ingest(places: list[dict[str, object]]) -> bool:
                """Add unseen places by placeId. Returns True once cap is hit."""
                for p in places:
                    pid = str(
                        p.get("placeId") or p.get("cid") or p.get("title") or ""
                    )
                    if not pid or pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    collected.append(p)
                    if len(collected) >= per_search_cap:
                        return True
                return False

            # Phase 1: primary call with the user's location text.
            initial = await _call_maps(term, location_str=loc)
            if _ingest(initial) or not initial:
                return term, loc, collected

            # Phase 2: fan out to a lat/lng grid centered on the seed results.
            # Serper /maps caps at 20 per call regardless of num/page/zoom, so
            # the only way to exceed 20 is to vary the geographic anchor.
            # Lat/lng grid works globally (no country-specific address parsing)
            # and is clamped to max_radius_km of the seed centroid so tiles
            # can't drift into unrelated regions even when the seed has
            # outliers or the user's input covers a huge area.
            if not expand:
                return term, loc, collected

            tile_centers = _tile_centers_from_seed(
                initial,
                max_tiles=expansion_cap,
                max_radius_km=expansion_radius_km,
            )
            if not tile_centers:
                return term, loc, collected

            tile_lls = [_format_ll(lat, lng) for lat, lng in tile_centers]
            logger.info(
                "MAPS EXPAND: term='%s' base='%s' seed=%d unique, %d tiles within %.0fkm: %s",
                term, loc, len(collected), len(tile_lls),
                expansion_radius_km, tile_lls,
            )

            expansions = await asyncio.gather(
                *[_call_maps(term, ll=coord) for coord in tile_lls]
            )
            for places in expansions:
                if _ingest(places):
                    break

            logger.info(
                "MAPS EXPAND DONE: term='%s' base='%s' total unique=%d",
                term, loc, len(collected),
            )
            return term, loc, collected

        raw_outcomes = await asyncio.gather(
            *[_search_one(s) for s in searches],
            return_exceptions=True,
        )

    all_places: list[dict[str, object]] = []
    seen_domains: set[str] = set()
    seen_names: set[str] = set()

    for outcome in raw_outcomes:
        if isinstance(outcome, BaseException):
            logger.warning("batch_search_maps outcome error: %s", outcome)
            continue
        term, loc, places = outcome
        for place in places:
            website = str(place.get("website") or "")
            domain = _parse_domain(website) if website else ""

            if domain:
                if domain in seen_domains:
                    continue
                seen_domains.add(domain)
            else:
                name_key = f"{str(place.get('title', '')).lower()}|{loc.lower()}"
                if name_key in seen_names:
                    continue
                seen_names.add(name_key)

            place["search_term"] = term
            place["location"] = loc
            all_places.append(place)

    return all_places

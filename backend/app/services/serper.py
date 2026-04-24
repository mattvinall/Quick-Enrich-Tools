import asyncio
import logging
import re
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.retry import retry_async

logger = logging.getLogger(__name__)

# Matches the "City, ST 12345" tail of a US address. Capture groups: city, state.
# Anchored to the ZIP so we don't grab street-address fragments like "SW 32nd Ave".
_CITY_STATE_RE = re.compile(r"([A-Z][A-Za-z .\-']{1,40}),\s*([A-Z]{2})\s+\d{5}")


def _extract_nearby_cities(
    places: list[dict[str, object]],
    exclude_location: str,
    limit: int,
) -> list[str]:
    """Mine Google Maps addresses for unique 'City, ST' tuples to fan out to.

    Excludes any candidate whose text overlaps the user's original location
    (case-insensitive) so we don't waste a call re-fetching what we already
    pulled. Returns cities ordered by how often they appear in the seed
    results (most frequent first), tie-broken alphabetically.
    """
    exclude = exclude_location.strip().lower()
    counts: dict[str, int] = {}
    for p in places:
        address = str(p.get("address") or "")
        match = _CITY_STATE_RE.search(address)
        if not match:
            continue
        city = match.group(1).strip()
        state = match.group(2).strip()
        candidate = f"{city}, {state}"
        cand_lower = candidate.lower()
        # Skip when user's input location is already this city or contains it
        # ("Miami, FL" should not re-query "Miami, FL" or "Miami")
        if exclude and (exclude in cand_lower or cand_lower in exclude or
                        city.lower() in exclude):
            continue
        counts[candidate] = counts.get(candidate, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [c for c, _ in ordered[:limit]]


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
    api_key: str | None = None,
    page: int = 1,
) -> dict[str, object]:
    """Search Google Maps via the Serper /maps endpoint for a single page.

    Returns a dict with keys: query, places (list of place dicts), page.
    Results are cached by query + location + page for 3 days.
    """
    search_query = f"{query} in {location}" if location else query
    cache_key = make_cache_key("serper_maps", search_query.lower(), f"p{page}")
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("SERPER MAPS CACHE HIT: %s page=%d", search_query, page)
        return cached

    logger.info("SERPER MAPS SEARCH: %s page=%d", search_query, page)

    body: dict[str, object] = {"q": search_query, "hl": "en"}
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
    expand = settings.maps_expand_to_nearby_cities
    expansion_cap = settings.maps_expansion_max_cities

    async with httpx.AsyncClient() as client:

        async def _call_maps(term: str, location_str: str) -> list[dict[str, object]]:
            """Single /maps call with retry + semaphore. Returns [] on failure."""
            async with semaphore:
                try:
                    result = await retry_async(
                        lambda l=location_str: search_maps(
                            client, term, l, api_key=api_key, page=1
                        ),
                        max_retries=3,
                        base_delay=1.0,
                    )
                    return result.get("places") or []
                except Exception as exc:
                    logger.warning(
                        "Maps search failed for '%s in %s': %s",
                        term, location_str, exc,
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

            # Phase 1: primary call with the user's location.
            initial = await _call_maps(term, loc)
            if _ingest(initial) or not initial:
                return term, loc, collected

            # Phase 2: fan out to nearby cities mined from initial addresses.
            # Serper /maps caps at 20 per call and page 2+ is empirically empty,
            # so the only way to exceed 20 is to vary the location parameter.
            if not expand or not loc:
                return term, loc, collected

            nearby_cities = _extract_nearby_cities(
                initial, exclude_location=loc, limit=expansion_cap,
            )
            if not nearby_cities:
                return term, loc, collected

            logger.info(
                "MAPS EXPAND: term='%s' base='%s' seed=%d unique, fanning out to %d nearby: %s",
                term, loc, len(collected), len(nearby_cities), nearby_cities,
            )

            expansions = await asyncio.gather(
                *[_call_maps(term, city) for city in nearby_cities]
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

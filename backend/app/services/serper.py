import asyncio
import logging
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.retry import retry_async

logger = logging.getLogger(__name__)


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

    Returns a dict with keys: query, results, candidate_domain.
    Results are cached by company_name + location for cache_ttl_days days.
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
        json={"q": query, "num": 3},
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()

    organic: list[dict[str, object]] = data.get("organic", [])
    results: list[dict[str, object]] = []
    for item in organic[:3]:
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
) -> dict[str, object]:
    """Search Google Maps via the Serper /maps endpoint.

    Returns a dict with keys: query, places (list of place dicts).
    Results are cached by query + location for 3 days.
    """
    search_query = f"{query} in {location}" if location else query
    cache_key = make_cache_key("serper_maps", search_query.lower())
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("SERPER MAPS CACHE HIT: %s", search_query)
        return cached

    logger.info("SERPER MAPS SEARCH: %s", search_query)

    response = await client.post(
        "https://google.serper.dev/maps",
        headers={
            "X-API-KEY": api_key or settings.serper_api_key,
            "Content-Type": "application/json",
        },
        json={"q": search_query, "hl": "en"},
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()

    places: list[dict[str, object]] = data.get("places", [])
    payload: dict[str, object] = {"query": search_query, "places": places}
    await cache_set(cache_key, payload, 3)  # 3-day cache
    return payload


async def batch_search_maps(
    searches: list[dict[str, str]],
    max_per_search: int = 20,
    concurrency: int | None = None,
    api_key: str | None = None,
) -> list[dict[str, object]]:
    """Search Google Maps for multiple query+location pairs.

    Each search: {"search_term": str, "location": str}
    Returns a flat list of place dicts, each augmented with
    'search_term' and 'location' keys. Deduplicates by normalized domain.

    max_per_search is capped at 20 per query (single Serper page).
    """
    limit = concurrency if concurrency is not None else settings.serper_concurrency
    semaphore = asyncio.Semaphore(limit)

    async with httpx.AsyncClient() as client:

        async def _search_one(
            search: dict[str, str],
        ) -> tuple[str, str, list[dict[str, object]]]:
            term = search["search_term"]
            loc = search["location"]
            async with semaphore:
                try:
                    result = await retry_async(
                        lambda t=term, l=loc: search_maps(client, t, l, api_key=api_key),
                        max_retries=3,
                        base_delay=1.0,
                    )
                    return term, loc, result.get("places", [])[:max_per_search]
                except Exception as exc:
                    logger.warning("Maps search failed for '%s in %s': %s", term, loc, exc)
                    return term, loc, []

        raw_outcomes = await asyncio.gather(
            *[_search_one(s) for s in searches],
            return_exceptions=True,
        )

    all_places: list[dict[str, object]] = []
    seen_domains: set[str] = set()
    seen_names: set[str] = set()

    for outcome in raw_outcomes:
        if isinstance(outcome, BaseException):
            continue
        term, loc, places = outcome
        for place in places:
            website = str(place.get("website") or "")
            domain = _parse_domain(website) if website else ""

            # Dedup by domain, or by name+location if no website
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

            if len(all_places) >= settings.max_rows:
                return all_places

    return all_places

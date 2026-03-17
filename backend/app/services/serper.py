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
            "X-API-KEY": settings.serper_api_key,
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
                        lambda cn=company_name, loc=location: search_company(client, cn, loc),
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
            continue
        dedup_key, value = outcome
        if isinstance(value, BaseException):
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

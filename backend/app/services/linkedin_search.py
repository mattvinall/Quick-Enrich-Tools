"""LinkedIn profile search via Serper API.

Searches Google for `site:linkedin.com/in/ "name" "company"` to find
LinkedIn profile URLs. Supports batching, deduplication, caching, and
confidence scoring.
"""

import asyncio
import logging
import re
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.retry import retry_async

logger = logging.getLogger(__name__)


def _build_linkedin_query(full_name: str, company_name: str) -> str:
    """Build a Serper query targeting LinkedIn profile pages."""
    name = full_name.strip()
    company = company_name.strip()
    return f'site:linkedin.com/in/ "{name}" "{company}"'


def _extract_linkedin_url(results: list[dict]) -> str:
    """Return the first linkedin.com/in/ URL from Serper results, or empty string."""
    for r in results:
        link = r.get("link", "")
        if "linkedin.com/in/" in link.lower():
            # Strip query params and fragments
            parsed = urlparse(link)
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            # Remove trailing slash
            return clean.rstrip("/")
    return ""


def _score_confidence(
    linkedin_url: str,
    full_name: str,
    company_name: str,
    results: list[dict],
) -> float:
    """Score confidence that the LinkedIn URL belongs to the right person.

    0.0 = no results
    0.5 = URL found but name not in title
    0.8 = URL found and name in title
    0.9 = URL found, name in title, company in title or snippet
    """
    if not linkedin_url:
        return 0.0

    name_lower = full_name.strip().lower()
    company_lower = company_name.strip().lower()

    # Check first result (the one we picked)
    first = results[0] if results else {}
    title = str(first.get("title", "")).lower()
    snippet = str(first.get("snippet", "")).lower()

    name_in_title = name_lower in title
    company_in_context = company_lower in title or company_lower in snippet

    if name_in_title and company_in_context:
        return 0.9
    if name_in_title:
        return 0.8
    return 0.5


def _detect_separator(lines: list[str]) -> str:
    """Auto-detect the most common separator from the first 5 non-empty lines."""
    candidates = {", ": 0, " | ": 0, " - ": 0}
    sample = [l for l in lines if l.strip()][:5]

    for line in sample:
        for sep in candidates:
            if sep in line:
                candidates[sep] += 1

    best = max(candidates, key=candidates.get)
    if candidates[best] == 0:
        return ", "  # default fallback
    return best


def parse_people_input(lines: list[str]) -> tuple[list[dict], int]:
    """Parse paste-mode lines into structured items.

    Returns (items, error_count) where items is a list of
    {full_name, company_name} dicts and error_count is the number
    of lines that could not be parsed.
    """
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return [], 0

    sep = _detect_separator(non_empty)
    items: list[dict] = []
    errors = 0

    for line in non_empty:
        stripped = line.strip()
        if not stripped:
            continue

        if sep == ", ":
            # First comma splits name from company; remaining commas are part of company
            idx = stripped.find(",")
            if idx == -1:
                errors += 1
                continue
            name = stripped[:idx].strip()
            company = stripped[idx + 1:].strip()
        else:
            parts = stripped.split(sep, 1)
            if len(parts) < 2:
                # Fallback: try comma split for lines that don't use the detected separator
                idx = stripped.find(",")
                if idx == -1:
                    errors += 1
                    continue
                name = stripped[:idx].strip()
                company = stripped[idx + 1:].strip()
            else:
                name = parts[0].strip()
                company = parts[1].strip()

        if not name or not company:
            errors += 1
            continue

        items.append({"full_name": name, "company_name": company})

    return items, errors


async def search_linkedin_profile(
    client: httpx.AsyncClient,
    full_name: str,
    company_name: str,
    api_key: str | None = None,
) -> dict:
    """Search Serper for a person's LinkedIn profile.

    Returns: {linkedin_url, confidence, query, results}
    """
    cache_key = make_cache_key("linkedin", full_name.strip().lower(), company_name.strip().lower())
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("LINKEDIN CACHE HIT: %s @ %s", full_name, company_name)
        return cached

    query = _build_linkedin_query(full_name, company_name)
    logger.info("LINKEDIN SEARCH: %s", query)

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

    organic = data.get("organic", [])
    results = []
    for item in organic[:3]:
        results.append({
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "snippet": item.get("snippet", ""),
        })

    linkedin_url = _extract_linkedin_url(results)
    confidence = _score_confidence(linkedin_url, full_name, company_name, results)

    payload = {
        "linkedin_url": linkedin_url,
        "confidence": confidence,
        "query": query,
        "results": results,
    }
    await cache_set(cache_key, payload, settings.cache_ttl_days)
    return payload


async def batch_linkedin_search(
    rows: list[dict],
    concurrency: int | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """Batch search LinkedIn profiles with deduplication and caching.

    Each row must have 'full_name' and 'company_name' keys.
    Returns list of dicts with keys: row_index, linkedin_url, confidence, search_results.
    """
    limit = concurrency if concurrency is not None else settings.linkedin_search_concurrency
    semaphore = asyncio.Semaphore(limit)

    # Group by (name_lower, company_lower) for dedup
    groups: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        name = row.get("full_name", "").strip().lower()
        company = row.get("company_name", "").strip().lower()
        dedup_key = f"{name}|{company}"
        groups.setdefault(dedup_key, []).append(idx)

    unique_keys = list(groups.keys())

    async with httpx.AsyncClient() as client:

        async def _search_one(dedup_key: str) -> tuple[str, dict | BaseException]:
            name, _, company = dedup_key.partition("|")
            # Use original casing from first row in group
            first_idx = groups[dedup_key][0]
            orig_name = rows[first_idx].get("full_name", name)
            orig_company = rows[first_idx].get("company_name", company)
            async with semaphore:
                try:
                    result = await retry_async(
                        lambda n=orig_name, c=orig_company: search_linkedin_profile(
                            client, n, c, api_key=api_key
                        ),
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

    key_to_result: dict[str, dict | None] = {}
    for outcome in raw_outcomes:
        if isinstance(outcome, BaseException):
            continue
        dedup_key, value = outcome
        if isinstance(value, BaseException):
            key_to_result[dedup_key] = None
        else:
            key_to_result[dedup_key] = value

    output: list[dict] = []
    for dedup_key, indices in groups.items():
        search_result = key_to_result.get(dedup_key)
        linkedin_url = search_result["linkedin_url"] if search_result else ""
        confidence = search_result["confidence"] if search_result else 0.0
        for idx in indices:
            output.append({
                "row_index": idx,
                "linkedin_url": linkedin_url,
                "confidence": confidence,
                "search_results": search_result,
            })

    output.sort(key=lambda item: int(item["row_index"]))
    return output

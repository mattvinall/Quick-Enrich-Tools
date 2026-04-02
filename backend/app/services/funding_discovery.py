"""Funding discovery — finds companies funded today via Serper news + Gemini extraction."""

import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
import google.generativeai as genai

from app.config import settings
from app.services.cache import cache_get, cache_set, get_redis, make_cache_key
from app.services.retry import retry_async

logger = logging.getLogger(__name__)

_FUNDING_QUERIES = [
    'startup "raises" funding',
    '"Series A" OR "Series B" OR "Series C" funding round',
    '"seed round" OR "pre-seed" startup funding',
]

_EXTRACTION_SYSTEM = (
    "You are a startup funding news analyst. Extract structured funding round data "
    "from news headlines and snippets. Only extract genuine venture capital / private equity "
    "funding rounds. Filter out acquisitions, IPOs, grants, and mergers."
)

_EXTRACTION_PROMPT = """Extract structured funding data from the following news items.

Rules:
- Only extract genuine startup/company funding rounds (Seed, Series A-E+, venture debt, growth equity, pre-IPO).
- SKIP acquisitions, acqui-hires, mergers, IPOs, government grants, debt financing, stock buybacks. For these, set "is_funding_round" to false.
- "funding_amount" must include currency symbol and abbreviation (e.g., "$5.5M", "$291M"). If not mentioned, set to null.
- "funding_round" must be one of: "Pre-Seed", "Seed", "Series A", "Series B", "Series C", "Series D", "Series E+", "Growth", "Venture Debt", "Bridge", "Pre-IPO", "Unknown".
- "lead_investor": first/lead investor name, or null if not mentioned.
- "description_snippet": under 20 words about what the company does, or null.
- Preserve non-English company names exactly as written.

Return a JSON array. Each element: {{"item_index": int, "is_funding_round": bool, "company_name": str, "funding_amount": str|null, "funding_round": str, "lead_investor": str|null, "description_snippet": str|null}}

News items:
{items}"""

_BATCH_SIZE = 15


async def _fetch_funding_news(hours: int = 24) -> list[dict[str, str]]:
    """Run 3 Serper /news queries in parallel, merge and dedup by URL."""
    tbs = "qdr:d" if hours <= 24 else "qdr:2d"
    semaphore = asyncio.Semaphore(settings.serper_concurrency)

    async with httpx.AsyncClient() as client:

        async def _query(q: str) -> list[dict[str, str]]:
            async with semaphore:
                response = await retry_async(
                    lambda query=q: client.post(
                        "https://google.serper.dev/news",
                        headers={
                            "X-API-KEY": settings.serper_api_key,
                            "Content-Type": "application/json",
                        },
                        json={"q": query, "num": 100, "tbs": tbs},
                        timeout=15.0,
                    ),
                    max_retries=3,
                    base_delay=1.0,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("news", [])

        results = await asyncio.gather(
            *[_query(q) for q in _FUNDING_QUERIES],
            return_exceptions=True,
        )

    # Merge and dedup by link
    seen_urls: set[str] = set()
    articles: list[dict[str, str]] = []
    for result in results:
        if isinstance(result, BaseException):
            logger.warning("Funding news query failed: %s", result)
            continue
        for article in result:
            url = article.get("link", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                articles.append({
                    "title": article.get("title", ""),
                    "snippet": article.get("snippet", ""),
                    "link": url,
                    "source": article.get("source", ""),
                    "date": article.get("date", ""),
                })

    logger.info("Funding news: fetched %d unique articles from %d queries", len(articles), len(_FUNDING_QUERIES))
    return articles


async def _extract_funding_data(articles: list[dict[str, str]]) -> list[dict[str, object]]:
    """Use Gemini to extract structured funding data from news articles."""
    if not articles:
        return []

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    all_extracted: list[dict[str, object]] = []

    for batch_start in range(0, len(articles), _BATCH_SIZE):
        batch = articles[batch_start:batch_start + _BATCH_SIZE]

        items_text = "\n".join(
            f'- item_index={batch_start + i} | headline="{a["title"]}" | snippet="{a["snippet"]}"'
            for i, a in enumerate(batch)
        )

        prompt = _EXTRACTION_PROMPT.format(items=items_text)

        try:
            response = await retry_async(
                lambda p=prompt: asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: model.generate_content(
                        [_EXTRACTION_SYSTEM, p],
                        generation_config=genai.GenerationConfig(
                            response_mime_type="application/json",
                            temperature=0.1,
                        ),
                    ),
                ),
                max_retries=3,
                base_delay=1.0,
            )
            text = response.text.strip()
            parsed = json.loads(text)
            if isinstance(parsed, list):
                all_extracted.extend(parsed)
            else:
                logger.warning("Gemini returned non-list for funding extraction")
        except Exception as exc:
            logger.warning("Funding extraction batch failed: %s", exc)
            continue

    return all_extracted


def _deduplicate_companies(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    """Deduplicate by company name (case-insensitive), keep richest entry."""
    seen: dict[str, dict[str, object]] = {}
    for entry in entries:
        name = str(entry.get("company_name", "")).strip()
        if not name:
            continue
        key = name.lower()
        existing = seen.get(key)
        if existing is None:
            seen[key] = entry
        else:
            # Keep the one with more fields populated
            existing_score = sum(1 for v in existing.values() if v)
            new_score = sum(1 for v in entry.values() if v)
            if new_score > existing_score:
                seen[key] = entry
    return list(seen.values())


async def discover_funded_companies(hours: int = 24) -> list[dict[str, object]]:
    """Discover companies funded in the last N hours.

    Returns a list of dicts with keys: company_name, funding_amount,
    funding_round, lead_investor, description_snippet, source_url, source_name.

    Results are cached for 1 hour.
    """
    cache_key = make_cache_key("funding_discovery", str(hours))
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("FUNDING DISCOVERY CACHE HIT: %dh", hours)
        companies = cached.get("companies", [])
        if isinstance(companies, list):
            return companies

    articles = await _fetch_funding_news(hours)
    if not articles:
        return []

    extracted = await _extract_funding_data(articles)

    # Filter to actual funding rounds and merge with article data
    companies: list[dict[str, object]] = []
    for entry in extracted:
        if not entry.get("is_funding_round"):
            continue
        idx = entry.get("item_index", -1)
        if not isinstance(idx, int) or idx < 0 or idx >= len(articles):
            continue

        article = articles[idx]
        companies.append({
            "company_name": str(entry.get("company_name", "")),
            "funding_amount": entry.get("funding_amount"),
            "funding_round": str(entry.get("funding_round", "Unknown")),
            "lead_investor": entry.get("lead_investor"),
            "description_snippet": entry.get("description_snippet"),
            "source_url": article.get("link", ""),
            "source_name": article.get("source", ""),
        })

    companies = _deduplicate_companies(companies)

    # Cache for 1 hour
    payload = {
        "companies": companies,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    await cache_set(cache_key, payload, ttl_days=1)
    # Override TTL to 1 hour via redis directly
    try:
        r = get_redis()
        await r.expire(cache_key, 3600)
    except Exception:
        pass

    logger.info("Funding discovery: %d companies found in last %dh", len(companies), hours)
    return companies

"""Serper client: company website search + generic search."""

import logging
import os
from urllib.parse import urlparse

import httpx

from .retry import retry_async

logger = logging.getLogger(__name__)

SERPER_API_KEY = os.getenv("SERPER_API_KEY", "")


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.removeprefix("www.")
    except Exception:
        return ""


async def search_company_website(client: httpx.AsyncClient, company_name: str) -> str:
    """Return the top candidate domain for a company name, or empty string."""
    if not SERPER_API_KEY:
        return ""
    query = f'"{company_name}" official website'
    logger.info("SERPER: %s", query)
    response = await retry_async(
        lambda: client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": 5},
            timeout=15.0,
        ),
        max_retries=2,
    )
    response.raise_for_status()
    data = response.json()
    organic = data.get("organic", [])
    for item in organic:
        dom = _domain(item.get("link", ""))
        if dom and not any(
            dom.endswith(b) for b in (
                "linkedin.com", "facebook.com", "twitter.com", "x.com",
                "crunchbase.com", "glassdoor.com", "g2.com", "wikipedia.org",
                "youtube.com", "bloomberg.com", "reuters.com",
            )
        ):
            return dom
    return ""


async def serper_search(client: httpx.AsyncClient, query: str, num: int = 100) -> list[dict]:
    """Generic organic-search call."""
    if not SERPER_API_KEY:
        return []
    response = await retry_async(
        lambda: client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": num},
            timeout=15.0,
        ),
        max_retries=2,
    )
    response.raise_for_status()
    return response.json().get("organic", [])

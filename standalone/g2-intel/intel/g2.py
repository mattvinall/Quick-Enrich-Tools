"""Discover products in a G2 category: scrape.do (super+render) → Serper fallback."""

import asyncio
import logging
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from .scraper import scrape_page
from .serper import serper_search

logger = logging.getLogger(__name__)


def _slug_from_url(url: str) -> str:
    parts = urlparse(url).path.strip("/").split("/")
    if len(parts) >= 2 and parts[0] == "products":
        return parts[1]
    return ""


def _clean_name(title: str) -> str:
    name = title
    for suffix in (" Reviews", " Pricing", " - G2", " Alternatives", " Pros and Cons", " Features", " Details"):
        i = name.find(suffix)
        if i > 0:
            name = name[:i]
    name = re.sub(r"\s+\d{4}\s*$", "", name).strip()
    return name


def _parse_g2_html(html: str) -> list[dict]:
    """Parse product cards from a G2 category listing page."""
    soup = BeautifulSoup(html, "lxml")
    products: list[dict] = []
    cards = soup.select("[data-product-id]") or soup.select(".product-listing__card") or soup.select(".paper--product")
    for card in cards:
        name_el = card.select_one('a.product-listing__product-name') or card.select_one('[itemprop="name"]') or card.select_one('h3 a')
        if not name_el:
            continue
        name = name_el.get_text(strip=True)
        if not name:
            continue
        href = name_el.get("href", "")
        if href and not href.startswith("http"):
            href = f"https://www.g2.com{href}"
        slug = _slug_from_url(href)
        if not slug:
            continue
        products.append({"name": name, "g2_url": f"https://www.g2.com/products/{slug}", "slug": slug})
    return products


async def discover_via_scrape(client: httpx.AsyncClient, slug: str) -> list[dict] | None:
    url = f"https://www.g2.com/categories/{slug}"
    for super_proxy in (True, False):
        try:
            html = await scrape_page(client, url, render=True, super_proxy=super_proxy, block_resources=False)
            products = _parse_g2_html(html)
            if products:
                logger.info("G2 SCRAPE: %s → %d products (super=%s)", slug, len(products), super_proxy)
                return products
        except Exception as exc:
            logger.warning("G2 scrape fail %s (super=%s): %s: %s", slug, super_proxy, type(exc).__name__, exc)
    return None


async def discover_via_serper(client: httpx.AsyncClient, slug: str, category_name: str) -> list[dict]:
    """Fallback: search Google for G2 product URLs. Returns what the index coughs up (often ~10)."""
    queries = [
        f'site:g2.com/products "{category_name}"',
        f'site:g2.com/products {category_name} software reviews',
        f'site:g2.com/products best {category_name} tools',
        f'site:g2.com/products top {category_name} software',
    ]
    products: list[dict] = []
    seen: set[str] = set()
    for q in queries:
        try:
            results = await serper_search(client, q, num=100)
        except Exception as exc:
            logger.warning("G2 serper query fail: %s: %s", type(exc).__name__, exc)
            continue
        for r in results:
            link = r.get("link", "")
            if "g2.com/products/" not in link:
                continue
            slug_p = _slug_from_url(link)
            if not slug_p or slug_p in seen:
                continue
            path = urlparse(link).path.lower()
            if any(x in path for x in ("/competitors", "/compare", "/alternatives")):
                continue
            name = _clean_name(r.get("title", ""))
            if not name or len(name) < 2:
                continue
            seen.add(slug_p)
            products.append({"name": name, "g2_url": f"https://www.g2.com/products/{slug_p}", "slug": slug_p})
        logger.info("G2 SERPER: '%s' → %d total products", q, len(products))
    return products


async def discover_category(client: httpx.AsyncClient, slug: str, category_name: str) -> list[dict]:
    """Discover products in a category: try scrape.do first, fall back to Serper."""
    scraped = await discover_via_scrape(client, slug)
    if scraped:
        return scraped
    logger.info("G2 FALLBACK to Serper for %s", slug)
    return await discover_via_serper(client, slug, category_name)


async def discover_categories(categories: list[tuple[str, str]], concurrency: int = 3) -> list[dict]:
    """Discover products across multiple categories (slug, display_name) in parallel."""
    sem = asyncio.Semaphore(concurrency)
    all_products: list[dict] = []
    seen: set[str] = set()

    async with httpx.AsyncClient() as client:

        async def _one(slug: str, name: str) -> list[dict]:
            async with sem:
                return await discover_category(client, slug, name)

        results = await asyncio.gather(
            *(_one(s, n) for s, n in categories), return_exceptions=True
        )

    for (slug, _), r in zip(categories, results):
        if isinstance(r, BaseException):
            logger.warning("discover %s failed: %s", slug, r)
            continue
        for p in r:
            if p["slug"] in seen:
                continue
            seen.add(p["slug"])
            all_products.append({**p, "g2_category": slug})
    return all_products

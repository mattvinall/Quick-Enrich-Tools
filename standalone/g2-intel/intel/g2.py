"""Discover products in a G2 category: scrape.do (super+render) -> Serper fallback."""

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
    # Current G2 markup uses .product-card; older markup is kept as fallback.
    cards = (
        soup.select(".product-card")
        or soup.select("[data-product-id]")
        or soup.select(".product-listing__card")
        or soup.select(".paper--product")
    )
    for card in cards:
        name_el = (
            card.select_one('[itemprop="name"]')
            or card.select_one('.product-card__product-name')
            or card.select_one('a.product-listing__product-name')
            or card.select_one('h3 a')
        )
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            img = card.select_one('img[alt]')
            if img:
                name = img.get("alt", "").strip()
        if not name:
            continue
        url_el = (
            card.select_one('a.product-card__img[href]')
            or card.select_one('a.product-listing__product-name[href]')
            or (name_el if name_el and name_el.name == "a" else None)
        )
        href = url_el.get("href", "") if url_el else ""
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
            probe_soup = BeautifulSoup(html, "lxml")
            has_cards = bool(
                probe_soup.select_one('.product-card')
                or probe_soup.select_one('[data-product-id]')
                or probe_soup.select_one('.product-listing__card')
                or probe_soup.select_one('.paper--product')
            )
            products = _parse_g2_html(html)
            logger.info(
                "G2 SCRAPE: category=%s super=%s body_len=%d cards_present=%s parsed=%d",
                slug, super_proxy, len(html), has_cards, len(products),
            )
            if products:
                return products
            # No cards -> DataDome shell. Try next pass.
        except Exception as exc:
            logger.warning(
                "G2 SCRAPE fail: category=%s super=%s err=%s: %s",
                slug, super_proxy, type(exc).__name__, exc,
            )
    logger.info("G2 SCRAPE: category=%s -> scrape_failed=true", slug)
    return None


async def discover_via_serper(client: httpx.AsyncClient, slug: str, category_name: str) -> list[dict]:
    """Fallback: search Google for G2 product URLs with query expansion + pagination.

    Google's `site:g2.com/products` index is shallow per-query, so we use a
    diverse query set and paginate each. Standalone pilot hardcodes pages_per_query=3
    (mirrors backend `settings.g2_serper_pages_per_query`).
    """
    pages_per_query = 3  # hardcoded; backend uses settings.g2_serper_pages_per_query
    queries = [
        f'site:g2.com/products "{category_name}"',
        f'site:g2.com/products {category_name} software reviews',
        f'site:g2.com/products best {category_name} tools',
        f'site:g2.com/products top {category_name} software',
        f'site:g2.com/products "{category_name}" platform',
        f'site:g2.com/products "{category_name}" vendor',
        f'site:g2.com/products "G2 Grid" "{category_name}"',
        f'site:g2.com/products "{category_name}" 2026',
        f'site:g2.com/products "{category_name}" software company',
        f'site:g2.com/products "{category_name}" pricing',
    ]

    sem = asyncio.Semaphore(5)

    async def _run(query: str, page: int) -> tuple[str, int, list[dict]]:
        async with sem:
            try:
                results = await serper_search(client, query, num=100, page=page)
                return query, page, results
            except Exception as exc:
                logger.warning(
                    "G2 SERPER fail: query='%s' page=%d err=%s: %s",
                    query, page, type(exc).__name__, exc,
                )
                return query, page, []

    tasks = [_run(q, p) for q in queries for p in range(1, pages_per_query + 1)]
    pairs = await asyncio.gather(*tasks)

    products: list[dict] = []
    seen: set[str] = set()
    per_query_raw: dict[str, int] = {}
    per_query_slugs: dict[str, set[str]] = {q: set() for q in queries}

    for query, page, results in pairs:
        per_query_raw[query] = per_query_raw.get(query, 0) + len(results)
        logger.info(
            "G2 SERPER: category=%s query='%s' page=%d -> %d raw results",
            slug, query, page, len(results),
        )
        for r in results:
            link = r.get("link", "")
            if "g2.com/products/" not in link:
                continue
            slug_p = _slug_from_url(link)
            if not slug_p:
                continue
            path = urlparse(link).path.lower()
            if any(x in path for x in ("/competitors", "/compare", "/alternatives")):
                continue
            per_query_slugs[query].add(slug_p)
            if slug_p in seen:
                continue
            name = _clean_name(r.get("title", ""))
            if not name or len(name) < 2:
                continue
            seen.add(slug_p)
            products.append({"name": name, "g2_url": f"https://www.g2.com/products/{slug_p}", "slug": slug_p})

    for q in queries:
        logger.info(
            "G2 SERPER SUMMARY: category=%s query='%s' raw=%d unique_slugs=%d",
            slug, q, per_query_raw.get(q, 0), len(per_query_slugs[q]),
        )
    logger.info(
        "G2 SERPER TOTAL: category=%s queries=%d pages_per_query=%d -> %d unique slugs",
        slug, len(queries), pages_per_query, len(seen),
    )
    return products


async def discover_category(client: httpx.AsyncClient, slug: str, category_name: str) -> list[dict]:
    """Discover products in a category: try scrape.do first, fall back to Serper."""
    scraped = await discover_via_scrape(client, slug)
    if scraped:
        logger.info("G2 PATH: category=%s discovered_via=scrape products=%d", slug, len(scraped))
        return scraped
    logger.info("G2 FALLBACK to Serper for %s", slug)
    serper_products = await discover_via_serper(client, slug, category_name)
    via = "serper" if serper_products else "none"
    logger.info("G2 PATH: category=%s discovered_via=%s products=%d", slug, via, len(serper_products))
    return serper_products


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

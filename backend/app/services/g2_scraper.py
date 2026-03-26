"""G2 category product discovery via Serper (Google search).

G2 uses DataDome anti-bot which blocks direct scraping (even via Spider.cloud).
Instead, we use Serper to search `site:g2.com/products` for each category,
extract product names and G2 URLs from search results, and deduplicate.
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


def _extract_product_slug(url: str) -> str:
    """Extract the product slug from a G2 URL like g2.com/products/heyreach/reviews."""
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    # Expected: ['products', 'slug'] or ['products', 'slug', 'reviews']
    if len(parts) >= 2 and parts[0] == "products":
        return parts[1]
    return ""


def _clean_product_name(title: str) -> str:
    """Extract clean product name from a Serper title like 'HeyReach Reviews 2026'."""
    # Strip common G2 suffixes
    name = title
    for suffix in [
        " Reviews", " Pricing", " - G2", " Alternatives",
        " Pros and Cons", " Features", " Details",
        " Reviews, Prices", " Reviews &",
    ]:
        idx = name.find(suffix)
        if idx > 0:
            name = name[:idx]
    # Remove year patterns at the end
    name = re.sub(r"\s+\d{4}\s*$", "", name).strip()
    # Remove "Top 10 ... Alternatives & Competitors" pattern
    if name.lower().startswith("top "):
        match = re.match(r"^top \d+ (.+?)(?:\s+alternatives|\s+competitors)", name, re.I)
        if match:
            name = match.group(1).strip()
    return name


async def _serper_search(client: httpx.AsyncClient, query: str, num: int = 30) -> list[dict]:
    """Run a single Serper search and return organic results."""
    response = await retry_async(
        lambda: client.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": settings.serper_api_key,
                "Content-Type": "application/json",
            },
            json={"q": query, "num": num},
            timeout=15.0,
        ),
        max_retries=2,
        base_delay=1.0,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("organic", [])


def _parse_g2_products_from_results(results: list[dict]) -> list[dict]:
    """Parse G2 product entries from Serper organic results."""
    products: list[dict] = []
    seen_slugs: set[str] = set()

    for result in results:
        link = result.get("link", "")
        title = result.get("title", "")

        if "g2.com/products/" not in link:
            continue

        slug = _extract_product_slug(link)
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        # Skip non-product pages (alternatives, compare pages)
        path = urlparse(link).path.lower()
        if any(skip in path for skip in ("/competitors", "/compare", "/alternatives")):
            continue

        name = _clean_product_name(title)
        if not name or len(name) < 2 or len(name) > 200:
            continue

        g2_url = f"https://www.g2.com/products/{slug}"
        products.append({
            "name": name,
            "g2_url": g2_url,
            "rating": None,
            "review_count": None,
        })

    return products


async def discover_g2_category(
    client: httpx.AsyncClient,
    category_slug: str,
    category_name: str,
    max_products: int = 250,
    semaphore: asyncio.Semaphore | None = None,
) -> list[dict]:
    """Discover products in a G2 category using Serper searches.

    Fires multiple search queries to maximize coverage, then deduplicates.
    """
    cache_key = make_cache_key("g2_cat", category_slug, str(max_products))
    try:
        cached = await cache_get(cache_key)
        if cached is not None and isinstance(cached, dict):
            products = cached.get("products", [])
            logger.info("G2 CACHE HIT: %s (%d products)", category_slug, len(products))
            return products[:max_products]
    except Exception:
        pass  # Redis unavailable — continue without cache

    # Build search queries for this category
    # Multiple queries improve coverage since Google caps at ~100 results
    queries = [
        f'site:g2.com/products "{category_name}"',
        f'site:g2.com/products {category_name} software reviews',
    ]

    # For larger requests, add more query variations
    if max_products > 50:
        queries.append(f'site:g2.com/products best {category_name} tools')
        queries.append(f'g2.com/products {category_name} 2025 2026')

    all_products: list[dict] = []
    seen_slugs: set[str] = set()

    for query in queries:
        try:
            if semaphore:
                async with semaphore:
                    results = await _serper_search(client, query, num=30)
            else:
                results = await _serper_search(client, query, num=30)

            products = _parse_g2_products_from_results(results)
            for p in products:
                slug = _extract_product_slug(p["g2_url"])
                if slug not in seen_slugs:
                    seen_slugs.add(slug)
                    all_products.append(p)

            logger.info("G2 SEARCH: '%s' → %d new products (total: %d)", query, len(products), len(all_products))

            if len(all_products) >= max_products:
                break

        except Exception as exc:
            logger.warning("G2 Serper search failed for '%s': %s", query, exc)
            continue

    result = all_products[:max_products]

    # Cache results
    try:
        await cache_set(cache_key, {"products": result}, settings.g2_cache_ttl_days)
    except Exception:
        pass

    return result


async def batch_scrape_g2_categories(
    categories: list[str],
    max_per_category: int = 250,
) -> list[dict]:
    """Discover products across multiple G2 categories and deduplicate.

    Args:
        categories: List of category slugs.
        max_per_category: Max products per category.

    Returns:
        Deduplicated list of product dicts with 'g2_category' field.
    """
    from app.services.g2_categories import get_category_by_slug

    concurrency = settings.g2_scrape_concurrency
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient() as client:
        tasks = []
        for slug in categories:
            cat = get_category_by_slug(slug)
            name = cat["name"] if cat else slug.replace("-", " ").title()
            tasks.append(
                discover_g2_category(client, slug, name, max_per_category, semaphore)
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge and deduplicate across categories
    all_products: list[dict] = []
    seen_slugs: set[str] = set()

    for slug, result in zip(categories, results):
        if isinstance(result, BaseException):
            logger.warning("G2 category discovery failed for %s: %s", slug, result)
            continue
        for product in result:
            product_slug = _extract_product_slug(product.get("g2_url", ""))
            if product_slug and product_slug not in seen_slugs:
                seen_slugs.add(product_slug)
                all_products.append({
                    **product,
                    "g2_category": slug,
                })

    logger.info("G2 BATCH: %d unique companies from %d categories", len(all_products), len(categories))
    return all_products

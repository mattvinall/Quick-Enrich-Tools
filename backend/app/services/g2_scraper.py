"""G2 category product discovery via Serper (Google search).

G2 uses DataDome anti-bot which blocks direct scraping (even via Spider.cloud).
Instead, we use Serper to search `site:g2.com/products` for each category,
extract product names and G2 URLs from search results, and deduplicate.
"""

import asyncio
import logging
import re
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.retry import retry_async
from app.services.scraper import scrape_page

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


def _parse_g2_category_html(html: str) -> tuple[list[dict], int]:
    """Parse G2 category page HTML to extract product listings.

    Returns (products, total_pages).
    Each product: {name, website, g2_url, rating, review_count}.
    """
    soup = BeautifulSoup(html, "lxml")
    products: list[dict] = []

    cards = soup.select('[data-product-id]') or soup.select('.product-listing__card') or soup.select('.paper--product')

    for card in cards:
        try:
            name_el = card.select_one('a.product-listing__product-name') or card.select_one('[itemprop="name"]') or card.select_one('h3 a')
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            if not name or len(name) < 2:
                continue

            href = name_el.get("href", "")
            if href and not href.startswith("http"):
                href = f"https://www.g2.com{href}"
            slug = ""
            if "/products/" in href:
                parts = urlparse(href).path.strip("/").split("/")
                if len(parts) >= 2 and parts[0] == "products":
                    slug = parts[1]
            g2_url = f"https://www.g2.com/products/{slug}" if slug else href

            rating = None
            rating_el = card.select_one('[itemprop="ratingValue"]') or card.select_one('.star-wrapper__value')
            if rating_el:
                try:
                    rating = float(rating_el.get("content", "") or rating_el.get_text(strip=True))
                except (ValueError, TypeError):
                    pass

            review_count = None
            review_el = card.select_one('[itemprop="reviewCount"]') or card.select_one('.product-listing__review-count')
            if review_el:
                text = review_el.get("content", "") or review_el.get_text(strip=True)
                nums = re.findall(r"[\d,]+", text)
                if nums:
                    try:
                        review_count = int(nums[0].replace(",", ""))
                    except ValueError:
                        pass

            website = None
            website_el = card.select_one('a[href*="visit_website"]') or card.select_one('.product-listing__website')
            if website_el:
                ws_href = website_el.get("href", "")
                if "url=" in ws_href:
                    qs = parse_qs(urlparse(ws_href).query)
                    ws_href = qs.get("url", [ws_href])[0]
                if ws_href.startswith("http"):
                    parsed = urlparse(ws_href)
                    website = parsed.netloc.removeprefix("www.")

            products.append({
                "name": name,
                "website": website,
                "g2_url": g2_url,
                "rating": rating,
                "review_count": review_count,
            })
        except Exception as exc:
            logger.debug("Failed to parse G2 product card: %s", exc)
            continue

    total_pages = 1
    pagination = soup.select('a[aria-label*="Page"]') or soup.select('.pagination a')
    for link in pagination:
        text = link.get_text(strip=True)
        try:
            page_num = int(text)
            total_pages = max(total_pages, page_num)
        except ValueError:
            continue

    return products, total_pages


async def discover_g2_category_via_scrape(
    client: httpx.AsyncClient,
    category_slug: str,
    category_name: str,
    max_products: int = 250,
    semaphore: asyncio.Semaphore | None = None,
) -> list[dict] | None:
    """Discover G2 products by scraping category listing pages via scrape.do.

    Returns list of product dicts, or None if scraping failed (caller should fallback to Serper).
    """
    cache_key = make_cache_key("g2_cat_scrape", category_slug, str(max_products))
    try:
        cached = await cache_get(cache_key)
        if cached is not None and isinstance(cached, dict):
            products = cached.get("products", [])
            logger.info("G2 SCRAPE CACHE HIT: %s (%d products)", category_slug, len(products))
            return products[:max_products]
    except Exception:
        pass

    all_products: list[dict] = []
    seen_slugs: set[str] = set()
    max_pages = min(
        max(1, (max_products + 24) // 25),
        settings.g2_max_pages_per_category,
    )

    for page in range(1, max_pages + 1):
        url = f"https://www.g2.com/categories/{category_slug}"
        if page > 1:
            url += f"?page={page}"

        try:
            if semaphore:
                async with semaphore:
                    html = await scrape_page(client, url, render=True)
            else:
                html = await scrape_page(client, url, render=True)
        except Exception as exc:
            logger.warning("G2 scrape.do failed for %s page %d: %s", category_slug, page, exc)
            if page == 1:
                return None
            break

        products, total_pages = _parse_g2_category_html(html)

        if not products:
            if page == 1:
                return None
            break

        for p in products:
            slug = _extract_product_slug(p.get("g2_url", ""))
            if slug and slug not in seen_slugs:
                seen_slugs.add(slug)
                all_products.append(p)

        logger.info(
            "G2 SCRAPE: %s page %d → %d products (total: %d)",
            category_slug, page, len(products), len(all_products),
        )

        if len(all_products) >= max_products:
            break
        if len(products) < 25:
            break
        if page >= total_pages:
            break

        await asyncio.sleep(1.5)

    result = all_products[:max_products]

    try:
        await cache_set(cache_key, {"products": result}, settings.g2_cache_ttl_days)
    except Exception:
        pass

    return result if result else None


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
        f'site:g2.com/products best {category_name} tools',
        f'site:g2.com/products {category_name} alternatives',
        f'site:g2.com/products top {category_name} software 2025 2026',
        f'g2.com/products {category_name}',
    ]

    all_products: list[dict] = []
    seen_slugs: set[str] = set()

    for query in queries:
        try:
            if semaphore:
                async with semaphore:
                    results = await _serper_search(client, query, num=100)
            else:
                results = await _serper_search(client, query, num=100)

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
    on_progress: object = None,
) -> list[dict]:
    """Discover products across multiple G2 categories.

    Tries scrape.do first for each category, falls back to Serper on failure.
    Deduplicates across all categories and sources.
    """
    from app.services.g2_categories import get_category_by_slug

    concurrency = settings.g2_scrape_concurrency
    semaphore = asyncio.Semaphore(concurrency)

    all_products: list[dict] = []
    seen_slugs: set[str] = set()
    failed_categories: list[tuple[str, str]] = []
    done_count = 0

    async with httpx.AsyncClient() as client:
        async def _scrape_one(slug: str, name: str) -> tuple[str, list[dict] | None]:
            result = await discover_g2_category_via_scrape(
                client, slug, name, max_per_category, semaphore
            )
            return slug, result

        tasks = []
        for slug in categories:
            cat = get_category_by_slug(slug)
            name = cat["name"] if cat else slug.replace("-", " ").title()
            tasks.append(_scrape_one(slug, name))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for slug, result in zip(categories, results):
            cat = get_category_by_slug(slug)
            name = cat["name"] if cat else slug.replace("-", " ").title()

            if isinstance(result, BaseException):
                logger.warning("G2 scrape.do exception for %s: %s", slug, result)
                failed_categories.append((slug, name))
            else:
                _, products = result
                if products is None:
                    failed_categories.append((slug, name))
                else:
                    for p in products:
                        product_slug = _extract_product_slug(p.get("g2_url", ""))
                        if product_slug and product_slug not in seen_slugs:
                            seen_slugs.add(product_slug)
                            all_products.append({**p, "g2_category": slug})

            done_count += 1
            if on_progress:
                try:
                    await on_progress(done_count, len(categories))
                except Exception:
                    pass

        if failed_categories:
            logger.info("G2: %d categories falling back to Serper: %s",
                len(failed_categories), [s for s, _ in failed_categories])

            for slug, name in failed_categories:
                try:
                    serper_products = await discover_g2_category(
                        client, slug, name, max_per_category, semaphore
                    )
                    for p in serper_products:
                        product_slug = _extract_product_slug(p.get("g2_url", ""))
                        if product_slug and product_slug not in seen_slugs:
                            seen_slugs.add(product_slug)
                            all_products.append({**p, "g2_category": slug})
                except Exception as exc:
                    logger.warning("G2 Serper fallback failed for %s: %s", slug, exc)

    logger.info("G2 BATCH: %d unique companies from %d categories", len(all_products), len(categories))
    return all_products

"""G2 category product discovery.

Primary path scrapes g2.com/categories/{slug} via scrape.do (rendered) and
paginates through `?page=N`, pulling ~15 products per page from the
`.product-card` markup. Serper is used as a fallback when scraping fails,
searching `site:g2.com/products` with a set of query variants + pagination.
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


async def _serper_search(
    client: httpx.AsyncClient,
    query: str,
    num: int = 30,
    page: int = 1,
) -> list[dict]:
    """Run a single Serper search and return organic results."""
    body: dict[str, object] = {"q": query, "num": num}
    if page > 1:
        body["page"] = page
    response = await retry_async(
        lambda: client.post(
            "https://google.serper.dev/search",
            headers={
                "X-API-KEY": settings.serper_api_key,
                "Content-Type": "application/json",
            },
            json=body,
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


_RATING_RE = re.compile(r"(\d\.\d)\s*out of 5")
_REVIEW_COUNT_RE = re.compile(r"\(([\d,]+)\)")


def _parse_g2_category_html(html: str) -> tuple[list[dict], int]:
    """Parse G2 category page HTML to extract product listings.

    Returns (products, total_pages).
    Each product: {name, website, g2_url, rating, review_count}.
    """
    soup = BeautifulSoup(html, "lxml")
    products: list[dict] = []

    # Current markup uses .product-card; older markup used the ones below. Keep
    # legacy selectors as fallback so a markup revert doesn't silently break us.
    cards = (
        soup.select('.product-card')
        or soup.select('[data-product-id]')
        or soup.select('.product-listing__card')
        or soup.select('.paper--product')
    )

    for card in cards:
        try:
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
            if not name or len(name) < 2:
                continue

            url_el = (
                card.select_one('a.product-card__img[href]')
                or card.select_one('a.product-listing__product-name[href]')
                or (name_el if name_el and name_el.name == "a" else None)
            )
            href = url_el.get("href", "") if url_el else ""
            if href and not href.startswith("http"):
                href = f"https://www.g2.com{href}"
            slug = ""
            if "/products/" in href:
                parts = urlparse(href).path.strip("/").split("/")
                if len(parts) >= 2 and parts[0] == "products":
                    slug = parts[1]
            if not slug:
                continue
            g2_url = f"https://www.g2.com/products/{slug}"

            card_text = card.get_text(" ", strip=True)

            rating: float | None = None
            rating_el = card.select_one('[itemprop="ratingValue"]') or card.select_one('.star-wrapper__value')
            if rating_el:
                try:
                    rating = float(rating_el.get("content", "") or rating_el.get_text(strip=True))
                except (ValueError, TypeError):
                    rating = None
            if rating is None:
                m = _RATING_RE.search(card_text)
                if m:
                    try:
                        rating = float(m.group(1))
                    except ValueError:
                        rating = None

            review_count: int | None = None
            review_el = card.select_one('[itemprop="reviewCount"]') or card.select_one('.product-listing__review-count')
            if review_el:
                text = review_el.get("content", "") or review_el.get_text(strip=True)
                nums = re.findall(r"[\d,]+", text)
                if nums:
                    try:
                        review_count = int(nums[0].replace(",", ""))
                    except ValueError:
                        review_count = None
            if review_count is None:
                m = _REVIEW_COUNT_RE.search(card_text)
                if m:
                    try:
                        review_count = int(m.group(1).replace(",", ""))
                    except ValueError:
                        review_count = None

            website: str | None = None
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

    # Pagination parsing is best-effort; G2's markup has changed repeatedly and
    # silent parse failures previously capped discovery at page 1. Try several
    # candidate selectors; the caller also stops when a page returns no new products,
    # so total_pages is advisory rather than authoritative.
    total_pages = 1
    pagination_selectors = [
        'a[aria-label*="Page"]',
        'a[aria-label*="page"]',
        '.pagination a',
        'nav[aria-label*="pagination" i] a',
        'a[data-pagination]',
        'a[href*="page="]',
    ]
    pagination: list = []
    for sel in pagination_selectors:
        pagination = soup.select(sel)
        if pagination:
            break

    for link in pagination:
        text = link.get_text(strip=True)
        try:
            page_num = int(text)
            total_pages = max(total_pages, page_num)
            continue
        except ValueError:
            pass
        # Fallback: extract from the href ?page=N
        href = link.get("href", "") or ""
        m = re.search(r"[?&]page=(\d+)", href)
        if m:
            try:
                total_pages = max(total_pages, int(m.group(1)))
            except ValueError:
                pass

    if not pagination and products:
        logger.info(
            "G2 PAGINATION: no pagination links matched any selector; relying on "
            "products-per-page heuristic to decide stop. products_on_page=%d",
            len(products),
        )

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
    cache_key = make_cache_key("g2_cat_scrape_v3", category_slug, str(max_products))
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
    # G2 renders 15 products per category page; cap by the configured ceiling.
    max_pages = min(
        max(1, (max_products + 14) // 15),
        settings.g2_max_pages_per_category,
    )

    for page in range(1, max_pages + 1):
        url = f"https://www.g2.com/categories/{category_slug}"
        if page > 1:
            url += f"?page={page}"

        html: str | None = None
        status = "unknown"
        # Two passes: super+render with resources on, then plain render as a second try.
        # If the first returns HTML without product cards (DataDome JS-gate), we retry.
        for attempt_idx, super_proxy in enumerate((True, False)):
            try:
                if semaphore:
                    async with semaphore:
                        candidate = await scrape_page(
                            client, url, render=True, super_proxy=super_proxy, block_resources=False,
                        )
                else:
                    candidate = await scrape_page(
                        client, url, render=True, super_proxy=super_proxy, block_resources=False,
                    )
                status = "ok"
                body_len = len(candidate)
                # Parse the DOM to check for real product cards. String matching
                # produced false positives (stray JS mentions of data-product-id).
                probe_soup = BeautifulSoup(candidate, "lxml")
                has_cards = bool(
                    probe_soup.select_one('.product-card')
                    or probe_soup.select_one('[data-product-id]')
                    or probe_soup.select_one('.product-listing__card')
                    or probe_soup.select_one('.paper--product')
                )
                logger.info(
                    "G2 SCRAPE.DO: category=%s page=%d super=%s status=%s body_len=%d cards_present=%s",
                    category_slug, page, super_proxy, status, body_len, has_cards,
                )
                html = candidate
                if has_cards:
                    break
                # Empty shell (DataDome JS-gate): try next pass with different render option
                logger.info(
                    "G2 SCRAPE.DO: no product cards found on attempt %d for %s page %d, retrying",
                    attempt_idx + 1, category_slug, page,
                )
            except Exception as exc:
                status = f"{type(exc).__name__}"
                logger.warning(
                    "G2 SCRAPE.DO failed: category=%s page=%d super=%s status=%s err=%s",
                    category_slug, page, super_proxy, status, exc,
                )
                continue

        if html is None:
            # All scrape.do attempts raised. Signal fallback by returning None.
            logger.info(
                "G2 SCRAPE.DO: category=%s page=%d -> scrape_failed=true (all attempts raised)",
                category_slug, page,
            )
            if page == 1:
                return None
            break

        products, total_pages = _parse_g2_category_html(html)
        logger.info(
            "G2 SCRAPE.DO PARSE: category=%s page=%d -> %d products parsed (total_pages=%d)",
            category_slug, page, len(products), total_pages,
        )

        if not products:
            # HTML returned but no product cards — treat as scrape failure on page 1
            if page == 1:
                logger.info(
                    "G2 SCRAPE.DO: category=%s -> scrape_failed=true (0 products parsed on page 1)",
                    category_slug,
                )
                return None
            break

        for p in products:
            slug = _extract_product_slug(p.get("g2_url", ""))
            if slug and slug not in seen_slugs:
                seen_slugs.add(slug)
                all_products.append(p)

        logger.info(
            "G2 SCRAPE: %s page %d -> %d products (total: %d)",
            category_slug, page, len(products), len(all_products),
        )

        if len(all_products) >= max_products:
            break
        # Stop if this page added no new unique products (dedup exhausted).
        added_this_page = len([
            p for p in products
            if _extract_product_slug(p.get("g2_url", "")) in seen_slugs
        ])
        # If the page returned a full batch (~15) keep paginating even when
        # total_pages reported a lower ceiling — the pagination selector may
        # simply not have matched G2's current markup.
        if len(products) < 10 and added_this_page < 1:
            break
        # Only trust total_pages as a hard stop when pagination links were
        # actually found; otherwise we fall back to empty-page detection above.
        if total_pages > 1 and page >= total_pages:
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

    # Build search queries for this category.
    # Google's site:g2.com/products index is shallow per-query, so we use a
    # diverse set of phrasings + paginate each one to maximize coverage.
    queries = [
        f'site:g2.com/products "{category_name}"',
        f'site:g2.com/products {category_name} software reviews',
        f'site:g2.com/products best {category_name} tools',
        f'site:g2.com/products {category_name} alternatives',
        f'site:g2.com/products top {category_name} software 2025 2026',
        f'g2.com/products {category_name}',
        f'site:g2.com/products "{category_name}" platform',
        f'site:g2.com/products "{category_name}" vendor',
        f'site:g2.com/products "G2 Grid" "{category_name}"',
        f'site:g2.com/products "{category_name}" 2026',
        f'site:g2.com/products "{category_name}" software company',
        f'site:g2.com/products "{category_name}" pricing',
    ]

    page_cap = settings.g2_serper_pages_per_query

    async def _run_query_page(query: str, page: int) -> tuple[str, int, list[dict]]:
        """Run a single (query, page) Serper call. Swallows exceptions."""
        try:
            if semaphore:
                async with semaphore:
                    results = await _serper_search(client, query, num=100, page=page)
            else:
                results = await _serper_search(client, query, num=100, page=page)
            return query, page, results
        except Exception as exc:
            logger.warning(
                "G2 SERPER failed: query='%s' page=%d err=%s: %s",
                query, page, type(exc).__name__, exc,
            )
            return query, page, []

    # Fire all (query, page) pairs concurrently — the existing semaphore
    # already gates overall G2 concurrency.
    tasks = [
        _run_query_page(q, p)
        for q in queries
        for p in range(1, page_cap + 1)
    ]
    query_results = await asyncio.gather(*tasks)

    # Per-query aggregation for logging: total raw results, unique slugs this query contributed.
    per_query_raw: dict[str, int] = {}
    per_query_slugs: dict[str, set[str]] = {q: set() for q in queries}

    all_products: list[dict] = []
    seen_slugs: set[str] = set()

    for query, page, results in query_results:
        per_query_raw[query] = per_query_raw.get(query, 0) + len(results)
        logger.info(
            "G2 SERPER: category=%s query='%s' page=%d -> %d raw results",
            category_slug, query, page, len(results),
        )
        products = _parse_g2_products_from_results(results)
        for p in products:
            slug = _extract_product_slug(p["g2_url"])
            if not slug:
                continue
            per_query_slugs[query].add(slug)
            if slug not in seen_slugs:
                seen_slugs.add(slug)
                all_products.append(p)
                if len(all_products) >= max_products:
                    break

    for q in queries:
        logger.info(
            "G2 SERPER SUMMARY: category=%s query='%s' raw=%d unique_slugs=%d",
            category_slug, q, per_query_raw.get(q, 0), len(per_query_slugs[q]),
        )
    logger.info(
        "G2 SERPER TOTAL: category=%s queries=%d pages_per_query=%d -> %d unique slugs",
        category_slug, len(queries), page_cap, len(seen_slugs),
    )

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
    # Track which path yielded products for each category (for final summary).
    scraped_ok: set[str] = set()

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
                    scraped_ok.add(slug)
                    added = 0
                    for p in products:
                        product_slug = _extract_product_slug(p.get("g2_url", ""))
                        if product_slug and product_slug not in seen_slugs:
                            seen_slugs.add(product_slug)
                            all_products.append({**p, "g2_category": slug})
                            added += 1
                    logger.info(
                        "G2 PATH: category=%s discovered_via=scrape products=%d added_unique=%d",
                        slug, len(products), added,
                    )

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
                    added = 0
                    for p in serper_products:
                        product_slug = _extract_product_slug(p.get("g2_url", ""))
                        if product_slug and product_slug not in seen_slugs:
                            seen_slugs.add(product_slug)
                            all_products.append({**p, "g2_category": slug})
                            added += 1
                    discovered_via = "serper" if slug not in scraped_ok else "both"
                    logger.info(
                        "G2 PATH: category=%s discovered_via=%s products=%d added_unique=%d",
                        slug, discovered_via, len(serper_products), added,
                    )
                except Exception as exc:
                    logger.warning("G2 Serper fallback failed for %s: %s", slug, exc)
                    logger.info(
                        "G2 PATH: category=%s discovered_via=none (scrape failed, serper raised)",
                        slug,
                    )

    logger.info("G2 BATCH: %d unique companies from %d categories", len(all_products), len(categories))
    return all_products

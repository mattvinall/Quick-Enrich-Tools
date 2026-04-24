"""Web scraper — crawl company websites and extract visible text.

Primary: scrape.do API (residential proxies, anti-bot bypass, JS rendering).
Fallback: Direct httpx if SCRAPE_DO_API_KEY is not set (free but lower success rate).
"""

import asyncio
import ipaddress
import logging
import random
import re
import socket
from urllib.parse import quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.retry import retry_async

logger = logging.getLogger(__name__)

_MAX_TEXT_PER_PAGE = 8_000
_MIN_CONTENT_LENGTH = 1500  # Below this, escalate to render+super proxy.
# Modern SPAs return 200-500 chars of React shell HTML on a basic fetch (nav,
# footer, no real content). Bump the threshold so those sites trigger Pass 2/3
# instead of silently feeding empty text to the LLM.

# Page URL patterns scored by relevance category
_HIGH_PATTERNS = re.compile(
    r"/(about|about-us|team|our-team|people|leadership|staff|contact|contact-us)(/|$)", re.I
)
_MEDIUM_PATTERNS = re.compile(
    r"/(services|products|solutions|what-we-do|offerings)(/|$)", re.I
)
_LOW_PATTERNS = re.compile(
    r"/(case-stud|clients|customers|portfolio|testimonials|partners|our-work|success-stories)(/|$)", re.I
)

# Option-to-priority mapping: which URL patterns matter for each extraction option
_OPTION_PRIORITIES = {
    "industry_description": [_HIGH_PATTERNS, _MEDIUM_PATTERNS],
    "target_market": [_LOW_PATTERNS, _MEDIUM_PATTERNS],
    "company_people": [_HIGH_PATTERNS],
    "homepage_raw_text": [],
}


# Rotating user agents — for direct httpx fallback
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

# Private/internal IP ranges to block (SSRF protection)
_BLOCKED_HOSTNAMES = {"localhost", "metadata.google.internal", "metadata.internal"}

# Domains known to use aggressive anti-bot protection (DataDome, PerimeterX, etc).
# For these, skip datacenter-proxy passes entirely — they always fail and waste
# credits, and repeated datacenter hits can poison scrape.do's IP pool for us.
_ANTIBOT_DOMAINS = {
    "g2.com", "linkedin.com", "crunchbase.com", "bloomberg.com",
    "zoominfo.com", "glassdoor.com", "reuters.com",
    # scrape.do explicitly 400s similarweb.com without super=true with the
    # message "You have to use super=True for Similarweb.com scraping. We
    # have custom solution :)" — skip the datacenter pass to avoid the waste.
    "similarweb.com",
}


def _is_antibot_domain(domain: str) -> bool:
    """Return True if domain (or its parent) is in the anti-bot whitelist."""
    d = domain.lower().removeprefix("www.")
    return any(d == ab or d.endswith("." + ab) for ab in _ANTIBOT_DOMAINS)


def _get_headers() -> dict[str, str]:
    """Return request headers with a randomly rotated User-Agent."""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _is_safe_url(url: str) -> bool:
    """Check URL is safe to fetch (not targeting internal/private networks).

    Prevents SSRF attacks when scraping user-provided URLs.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        if not hostname:
            return False

        # Block known internal hostnames
        if hostname.lower() in _BLOCKED_HOSTNAMES:
            return False

        # Only allow http/https
        if parsed.scheme not in ("http", "https"):
            return False

        # Resolve hostname and check for private IPs
        try:
            addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for _, _, _, _, sockaddr in addr_info:
                ip = sockaddr[0]
                ip_obj = ipaddress.ip_address(ip)
                if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                    logger.warning("SSRF blocked: %s resolves to private IP %s", hostname, ip)
                    return False
        except (socket.gaierror, ValueError):
            pass  # DNS resolution failed — let httpx handle it

        return True
    except Exception:
        return False


async def scrape_page(
    client: httpx.AsyncClient,
    url: str,
    render: bool = False,
    super_proxy: bool = False,
    block_resources: bool = True,
    api_key: str | None = None,
) -> str:
    """Scrape a single URL. Returns raw HTML string.

    Uses scrape.do API when a key is available (api_key arg overrides
    settings.scrape_do_api_key). Otherwise, fetches directly via httpx
    with a browser-like User-Agent.

    Args:
        render: Use headless browser for JS rendering (5 credits).
        super_proxy: Use residential proxy pool (10 credits, or 25 with render).
        block_resources: Block CSS/images/fonts (default True). Set False for
            sites that detect missing resources as bot behavior.
        api_key: Caller-provided Scrape.do token. Falls back to the configured
            server key when empty.
    """
    if not _is_safe_url(url):
        raise ValueError(f"URL blocked by SSRF protection: {url}")

    effective_scrape_do = (api_key or settings.scrape_do_api_key or "").strip()

    if effective_scrape_do:
        # scrape.do API — handles anti-bot, residential proxies, optional JS rendering
        encoded_url = quote(url, safe="")
        api_url = (
            f"https://api.scrape.do/"
            f"?token={effective_scrape_do}"
            f"&url={encoded_url}"
        )
        if render:
            api_url += "&render=true&waitUntil=networkidle2"
            if not block_resources:
                api_url += "&blockResources=false"
        if super_proxy:
            api_url += "&super=true"

        response = await retry_async(
            lambda: client.get(
                api_url,
                timeout=settings.scrape_timeout,
            ),
            max_retries=2,
            base_delay=1.0,
        )
        response.raise_for_status()
        return response.text

    # Direct fetch fallback (free, works for most company sites)
    response = await retry_async(
        lambda: client.get(
            url,
            headers=_get_headers(),
            follow_redirects=True,
            timeout=settings.scrape_timeout,
        ),
        max_retries=2,
        base_delay=1.0,
    )
    response.raise_for_status()
    return response.text


_GENERIC_EMAIL_PREFIXES = {
    "info", "contact", "hello", "support", "sales", "help",
    "admin", "office", "team", "general", "enquiries", "inquiries",
    "mail", "service", "billing", "hr", "careers", "press", "media",
}

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def extract_generic_emails(html: str) -> list[str]:
    """Extract generic company emails (info@, contact@, etc.) from raw HTML via regex."""
    all_emails = _EMAIL_RE.findall(html)
    seen: set[str] = set()
    result: list[str] = []
    for email in all_emails:
        lower = email.lower()
        prefix = lower.split("@")[0]
        if prefix in _GENERIC_EMAIL_PREFIXES and lower not in seen:
            seen.add(lower)
            result.append(lower)
    return result


def extract_text_from_html(html: str) -> str:
    """Strip HTML to visible text using BeautifulSoup.

    Removes scripts, styles, nav, footer, header elements.
    Extracts from <main>, <article>, or <body> in priority order.
    Truncates to _MAX_TEXT_PER_PAGE characters.
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove non-content elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()

    # Try to find main content area
    content = soup.find("main") or soup.find("article") or soup.find("body")
    if content is None:
        content = soup

    text = content.get_text(separator="\n", strip=True)

    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text[:_MAX_TEXT_PER_PAGE]


def discover_relevant_pages(
    html: str,
    domain: str,
    options: dict,
    max_pages: int = 5,
) -> list[str]:
    """Parse homepage HTML and return top internal page URLs sorted by relevance.

    Scores links by URL pattern matching against selected extraction options.
    Returns at most max_pages URLs (not including homepage).
    """
    soup = BeautifulSoup(html, "lxml")
    base_url = f"https://{domain}"

    scored: dict[str, int] = {}
    seen_paths: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        full_url = urljoin(base_url, href)

        parsed = urlparse(full_url)
        # Only same-domain internal links
        link_domain = parsed.netloc.removeprefix("www.")
        if link_domain != domain and link_domain != f"www.{domain}":
            continue

        path = parsed.path.rstrip("/")
        if not path or path == "/" or path in seen_paths:
            continue

        # Skip non-page resources
        if any(path.endswith(ext) for ext in (".pdf", ".jpg", ".png", ".gif", ".css", ".js", ".zip")):
            continue

        seen_paths.add(path)
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        score = 0
        for option_key, patterns in _OPTION_PRIORITIES.items():
            if not options.get(option_key, False):
                continue
            for i, pattern in enumerate(patterns):
                if pattern.search(path):
                    score += (3 - i)  # Higher score for higher priority patterns

        if score > 0:
            scored[clean_url] = max(scored.get(clean_url, 0), score)

    # Sort by score descending, take top max_pages
    sorted_urls = sorted(scored.keys(), key=lambda u: scored[u], reverse=True)
    return sorted_urls[:max_pages]


async def crawl_site(
    client: httpx.AsyncClient,
    domain: str,
    options: dict,
    max_pages: int | None = None,
    api_key: str | None = None,
) -> dict[str, str]:
    """Crawl a company website: homepage + relevant internal pages.

    Returns dict of {url: extracted_text}.
    """
    if max_pages is None:
        max_pages = settings.max_pages_per_site

    effective_scrape_do = (api_key or settings.scrape_do_api_key or "").strip()

    result: dict[str, str] = {}
    homepage_url = f"https://{domain}"

    # Step 1: Scrape homepage
    # Known anti-bot sites skip datacenter passes (always 403, wastes credits).
    # Everything else uses 3-pass escalation: datacenter → render → super+render.
    antibot = _is_antibot_domain(domain) and bool(effective_scrape_do)
    try:
        if antibot:
            logger.info("SCRAPE ANTIBOT (super+render): %s", domain)
            homepage_html = await scrape_page(
                client, homepage_url,
                render=True, super_proxy=True, block_resources=False,
                api_key=effective_scrape_do,
            )
            homepage_text = extract_text_from_html(homepage_html)
        else:
            # Pass 1: Normal datacenter proxy, no JS rendering (1 credit)
            homepage_html = await scrape_page(
                client, homepage_url, render=False, api_key=effective_scrape_do,
            )
            homepage_text = extract_text_from_html(homepage_html)

            # Pass 2: JS rendering if content too short (5 credits)
            if len(homepage_text) < _MIN_CONTENT_LENGTH and effective_scrape_do:
                try:
                    logger.info("SCRAPE PASS 2 (render): %s", domain)
                    homepage_html = await scrape_page(
                        client, homepage_url, render=True, api_key=effective_scrape_do,
                    )
                    homepage_text = extract_text_from_html(homepage_html)
                except Exception:
                    pass

            # Pass 3: Residential proxy + render + unblocked resources (25 credits)
            if len(homepage_text) < _MIN_CONTENT_LENGTH and effective_scrape_do:
                try:
                    logger.info("SCRAPE PASS 3 (super+render): %s", domain)
                    homepage_html = await scrape_page(
                        client, homepage_url,
                        render=True, super_proxy=True, block_resources=False,
                        api_key=effective_scrape_do,
                    )
                    homepage_text = extract_text_from_html(homepage_html)
                except Exception:
                    pass

        result[homepage_url] = homepage_text
    except Exception as exc:
        logger.warning(
            "Failed to scrape homepage for %s: %s: %s",
            domain, type(exc).__name__, exc,
        )
        return result

    # Step 2: Discover and scrape internal pages
    internal_urls = discover_relevant_pages(
        homepage_html, domain, options, max_pages=max_pages - 1
    )

    if internal_urls:
        sem = asyncio.Semaphore(5)  # Limit concurrency per site

        async def _scrape_internal(url: str) -> tuple[str, str]:
            async with sem:
                try:
                    html = await scrape_page(
                        client, url, render=False, api_key=effective_scrape_do,
                    )
                    return url, extract_text_from_html(html)
                except Exception as exc:
                    logger.debug("Failed to scrape %s: %s", url, exc)
                    return url, ""

        tasks = [_scrape_internal(u) for u in internal_urls]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                continue
            url, text = outcome
            if text:
                result[url] = text

    return result


async def batch_crawl(
    domains: list[str],
    options: dict,
    concurrency: int | None = None,
    api_key: str | None = None,
) -> dict[str, dict[str, str]]:
    """Crawl multiple company websites concurrently.

    Returns {domain: {url: text}} for each domain.
    Checks Redis cache first; caches results for cache_ttl_days.
    """
    limit = concurrency if concurrency is not None else settings.scrape_concurrency
    semaphore = asyncio.Semaphore(limit)

    results: dict[str, dict[str, str]] = {}

    async with httpx.AsyncClient() as client:

        async def _crawl_one(domain: str) -> tuple[str, dict[str, str]]:
            # Check cache
            cache_key = make_cache_key("scrape", domain.lower())
            cached = await cache_get(cache_key)
            if cached is not None and isinstance(cached, dict):
                logger.info("SCRAPE CACHE HIT: %s", domain)
                return domain, cached

            async with semaphore:
                pages = await crawl_site(client, domain, options, api_key=api_key)
                if pages:
                    await cache_set(cache_key, pages, settings.cache_ttl_days)
                return domain, pages

        tasks = [_crawl_one(d) for d in domains]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            logger.warning("batch_crawl error: %s", outcome)
            continue
        domain, pages = outcome
        results[domain] = pages

    return results

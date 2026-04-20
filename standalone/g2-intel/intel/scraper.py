"""Scrape URLs via scrape.do, extract visible text + discover relevant internal pages."""

import asyncio
import logging
import os
import re
from urllib.parse import parse_qs, quote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .retry import retry_async

logger = logging.getLogger(__name__)

SCRAPE_DO_API_KEY = os.getenv("SCRAPE_DO_API_KEY", "")
SCRAPE_TIMEOUT = float(os.getenv("SCRAPE_TIMEOUT", "60"))
MIN_CONTENT_LENGTH = 200
MAX_TEXT_PER_PAGE = 8_000

_ANTIBOT_DOMAINS = {
    "g2.com", "linkedin.com", "crunchbase.com", "bloomberg.com",
    "zoominfo.com", "glassdoor.com", "reuters.com",
}

_HIGH = re.compile(r"/(about|about-us|team|our-team|people|leadership|staff|contact|contact-us)(/|$)", re.I)
_MED = re.compile(r"/(services|products|solutions|what-we-do|offerings)(/|$)", re.I)
_LOW = re.compile(r"/(case-stud|clients|customers|portfolio|testimonials|partners|our-work|success-stories)(/|$)", re.I)

_OPTION_PRIORITIES = {
    "industry_description": [_HIGH, _MED],
    "target_market": [_LOW, _MED],
    "company_people": [_HIGH],
    "homepage_raw_text": [],
}


def _is_antibot(domain: str) -> bool:
    d = domain.lower().removeprefix("www.")
    return any(d == ab or d.endswith("." + ab) for ab in _ANTIBOT_DOMAINS)


async def scrape_page(
    client: httpx.AsyncClient,
    url: str,
    render: bool = False,
    super_proxy: bool = False,
    block_resources: bool = True,
) -> str:
    """Fetch URL via scrape.do (if key set) or direct httpx fallback. Returns HTML."""
    if SCRAPE_DO_API_KEY:
        api_url = (
            f"https://api.scrape.do/?token={SCRAPE_DO_API_KEY}&url={quote(url, safe='')}"
        )
        if render:
            api_url += "&render=true&waitUntil=networkidle2"
            if not block_resources:
                api_url += "&blockResources=false"
        if super_proxy:
            api_url += "&super=true"
        response = await retry_async(
            lambda: client.get(api_url, timeout=SCRAPE_TIMEOUT),
            max_retries=2,
        )
        response.raise_for_status()
        return response.text

    # Direct fallback — works for many company sites, not for DataDome-protected ones
    response = await retry_async(
        lambda: client.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"},
            follow_redirects=True,
            timeout=SCRAPE_TIMEOUT,
        ),
        max_retries=2,
    )
    response.raise_for_status()
    return response.text


def extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
        tag.decompose()
    content = soup.find("main") or soup.find("article") or soup.find("body") or soup
    text = content.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text[:MAX_TEXT_PER_PAGE]


def discover_relevant_pages(html: str, domain: str, options: dict, max_pages: int = 4) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    base = f"https://{domain}"
    scored: dict[str, int] = {}
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        full = urljoin(base, a["href"])
        p = urlparse(full)
        link_domain = p.netloc.removeprefix("www.")
        if link_domain != domain and link_domain != f"www.{domain}":
            continue
        path = p.path.rstrip("/")
        if not path or path == "/" or path in seen:
            continue
        if any(path.endswith(x) for x in (".pdf", ".jpg", ".png", ".gif", ".css", ".js", ".zip")):
            continue
        seen.add(path)
        clean = f"{p.scheme}://{p.netloc}{p.path}"
        score = 0
        for opt, patterns in _OPTION_PRIORITIES.items():
            if not options.get(opt):
                continue
            for i, pat in enumerate(patterns):
                if pat.search(path):
                    score += 3 - i
        if score > 0:
            scored[clean] = max(scored.get(clean, 0), score)

    return sorted(scored.keys(), key=lambda u: scored[u], reverse=True)[:max_pages]


async def crawl_site(
    client: httpx.AsyncClient,
    domain: str,
    options: dict,
    max_pages: int = 4,
) -> dict[str, str]:
    """Crawl homepage + top internal pages for a domain. Returns {url: text}."""
    result: dict[str, str] = {}
    homepage_url = f"https://{domain}"
    antibot = _is_antibot(domain) and bool(SCRAPE_DO_API_KEY)

    try:
        if antibot:
            logger.info("SCRAPE antibot (super+render): %s", domain)
            html = await scrape_page(client, homepage_url, render=True, super_proxy=True, block_resources=False)
            text = extract_text(html)
        else:
            # Pass 1: plain
            html = await scrape_page(client, homepage_url, render=False)
            text = extract_text(html)
            # Pass 2: render if short
            if len(text) < MIN_CONTENT_LENGTH and SCRAPE_DO_API_KEY:
                try:
                    html = await scrape_page(client, homepage_url, render=True)
                    text = extract_text(html)
                except Exception:
                    pass
            # Pass 3: super + render if still short
            if len(text) < MIN_CONTENT_LENGTH and SCRAPE_DO_API_KEY:
                try:
                    html = await scrape_page(client, homepage_url, render=True, super_proxy=True, block_resources=False)
                    text = extract_text(html)
                except Exception:
                    pass
        result[homepage_url] = text
    except Exception as exc:
        logger.warning("homepage fail %s: %s: %s", domain, type(exc).__name__, exc)
        return result

    # Internal pages
    internal = discover_relevant_pages(html, domain, options, max_pages=max_pages - 1)
    if internal:
        sem = asyncio.Semaphore(5)

        async def _scrape_internal(u: str) -> tuple[str, str]:
            async with sem:
                try:
                    h = await scrape_page(client, u, render=False)
                    return u, extract_text(h)
                except Exception:
                    return u, ""

        outcomes = await asyncio.gather(*(_scrape_internal(u) for u in internal), return_exceptions=True)
        for o in outcomes:
            if isinstance(o, BaseException):
                continue
            u, t = o
            if t:
                result[u] = t
    return result

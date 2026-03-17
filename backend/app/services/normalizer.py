"""Domain normalization pipeline."""

import asyncio

import httpx
import tldextract

from app.services.retry import retry_async

BLOCKED_DOMAINS: frozenset[str] = frozenset(
    {
        "facebook.com",
        "linkedin.com",
        "twitter.com",
        "x.com",
        "instagram.com",
        "youtube.com",
        "tiktok.com",
        "pinterest.com",
        "glassdoor.com",
        "yelp.com",
        "bbb.org",
        "crunchbase.com",
        "zoominfo.com",
        "yellowpages.com",
        "indeed.com",
        "reddit.com",
        "wikipedia.org",
        "bloomberg.com",
        "dnb.com",
    }
)


def clean_url(url: str) -> str | None:
    """Return a bare root domain from a raw URL string, or None if invalid.

    Pipeline:
    1. Strip whitespace, lowercase.
    2. Remove protocol (http://, https://).
    3. Remove www. prefix.
    4. Remove path, query, and fragment.
    5. Use tldextract to extract the root domain + suffix.
    6. Return "{domain}.{suffix}" or None when either part is missing.
    """
    url = url.strip().lower()

    # Remove protocol
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            url = url[len(prefix):]
            break

    # Remove www. prefix
    if url.startswith("www."):
        url = url[4:]

    # Remove path, query, and fragment
    for separator in ("/", "?", "#"):
        idx = url.find(separator)
        if idx != -1:
            url = url[:idx]

    extracted = tldextract.extract(url)
    if not extracted.domain or not extracted.suffix:
        return None

    return f"{extracted.domain}.{extracted.suffix}"


def is_blocked_domain(domain: str) -> bool:
    """Return True if domain is in the BLOCKED_DOMAINS frozenset."""
    return domain in BLOCKED_DOMAINS


def normalize_domain(raw_url: str) -> dict[str, str | bool | None]:
    """Normalize a raw URL into a validated domain result dict.

    Returns a dict with keys:
        domain  – cleaned domain string or None
        blocked – whether the domain is blocked
        error   – error message string or None
    """
    if not raw_url or not raw_url.strip():
        return {"domain": None, "blocked": False, "error": "empty input"}

    domain = clean_url(raw_url)
    if domain is None:
        return {"domain": None, "blocked": False, "error": "invalid URL"}

    # Validate that tldextract agrees the suffix is real
    extracted = tldextract.extract(domain)
    if not extracted.domain or not extracted.suffix:
        return {"domain": None, "blocked": False, "error": "invalid URL"}

    if is_blocked_domain(domain):
        return {"domain": None, "blocked": True, "error": f"blocked domain: {domain}"}

    return {"domain": domain, "blocked": False, "error": None}


async def resolve_redirect(client: httpx.AsyncClient, domain: str) -> str:
    """Follow redirects for https://{domain} and return the final root domain."""
    try:
        response = await retry_async(
            lambda: client.head(
                f"https://{domain}",
                follow_redirects=True,
                timeout=5,
            ),
            max_retries=2,
            base_delay=0.5,
        )
        final_url = str(response.url)
        cleaned = clean_url(final_url)
        return cleaned if cleaned is not None else domain
    except Exception:
        return domain


async def batch_normalize(
    rows: list[dict[str, str | None]],
    resolve_redirects: bool = True,
    concurrency: int = 50,
) -> list[dict[str, str | bool | int | None]]:
    """Normalize domains for a list of row dicts.

    Each row is expected to contain a ``verified_domain`` or ``raw_domain``
    key (``verified_domain`` takes precedence).

    Returns a list of dicts with keys:
        row_index – original index of the row
        domain    – resolved root domain or None
        blocked   – whether the domain is blocked
        error     – error message or None
    """
    semaphore = asyncio.Semaphore(concurrency)
    seen_redirects: dict[str, str] = {}

    async def _process_row(
        index: int,
        row: dict[str, str | None],
        client: httpx.AsyncClient,
    ) -> dict[str, str | bool | int | None]:
        raw = row.get("verified_domain") or row.get("raw_domain") or ""
        result = normalize_domain(raw)

        if result["error"] is not None or result["domain"] is None:
            return {"row_index": index, **result}

        domain: str = result["domain"]  # type: ignore[assignment]

        if resolve_redirects:
            async with semaphore:
                if domain in seen_redirects:
                    resolved = seen_redirects[domain]
                else:
                    resolved = await resolve_redirect(client, domain)
                    seen_redirects[domain] = resolved

            if resolved != domain:
                # Re-validate the resolved domain
                resolved_result = normalize_domain(resolved)
                if resolved_result["error"] is not None or resolved_result["blocked"]:
                    return {"row_index": index, **resolved_result}
                domain = resolved_result["domain"]  # type: ignore[assignment]

        return {"row_index": index, "domain": domain, "blocked": False, "error": None}

    async with httpx.AsyncClient() as client:
        tasks = [_process_row(i, row, client) for i, row in enumerate(rows)]
        return list(await asyncio.gather(*tasks))

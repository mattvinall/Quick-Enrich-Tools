import asyncio
import logging

import httpx

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.retry import retry_async

logger = logging.getLogger(__name__)

_CONTACT_FIELDS = ("title", "first_name", "last_name", "email", "phone", "linkedin_url")


def _enrich_cache_key(domain: str, job_titles: list[str], max_contacts: int) -> str:
    """Build a deterministic cache key for enrichment results."""
    sorted_titles = ", ".join(sorted(t.lower() for t in job_titles))
    return make_cache_key("enrich", domain.lower(), sorted_titles, str(max_contacts))


async def enrich_company(
    client: httpx.AsyncClient,
    domain: str,
    job_titles: list[str],
    max_contacts: int = 1,
) -> list[dict[str, str]]:
    """Fetch contacts from QuickEnrich for a single domain.

    Checks Redis cache first. On cache miss, calls the API and caches the result.
    """
    cache_key = _enrich_cache_key(domain, job_titles, max_contacts)
    cached = await cache_get(cache_key)
    if cached is not None and isinstance(cached, dict):
        logger.info("ENRICH CACHE HIT: %s", domain)
        return cached.get("contacts", [])  # type: ignore[return-value]

    contacts: list[dict[str, str]] = []
    seen_keys: set[str] = set()

    async def _do_request(title: str) -> httpx.Response:
        response = await client.get(
            "https://app.quickenrich.io/api/employees/dataset-search",
            params={"company_url": domain, "title": title},
            headers={"Authorization": f"Bearer {settings.quickenrich_api_key}"},
            timeout=15.0,
        )
        response.raise_for_status()
        return response

    try:
        # Make individual API calls per title and merge results
        for title in job_titles:
            response = await retry_async(
                lambda t=title: _do_request(t), max_retries=3, base_delay=1.0
            )
            data = response.json()

            if isinstance(data, list):
                raw_results: list[dict[str, object]] = data
            elif isinstance(data, dict):
                raw_results = data.get("data", data.get("results", []))
            else:
                raw_results = []

            for record in raw_results[:max_contacts]:
                # Deduplicate by email or full name to avoid repeats across title queries
                email = str(record.get("email") or "")
                first = str(record.get("first_name") or "")
                last = str(record.get("last_name") or "")
                dedup_key = email.lower() if email and email != "N/A" else f"{first}|{last}".lower()

                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                contacts.append(
                    {
                        "title": str(record.get("title") or ""),
                        "first_name": first,
                        "last_name": last,
                        "email": email,
                        "phone": str(record.get("employee_phone") or record.get("phone") or ""),
                        "linkedin_url": str(
                            record.get("employee_linkedin") or record.get("linkedin_url") or ""
                        ),
                    }
                )

        # Only cache successful results — never cache on error
        await cache_set(cache_key, {"contacts": contacts}, settings.cache_ttl_days)
    except Exception as exc:
        logger.warning("enrich_company error for domain=%s titles=%s: %s", domain, job_titles, exc)

    return contacts


async def batch_enrich(
    domains_with_rows: dict[str, list[int]],
    job_titles: list[str],
    max_contacts: int = 1,
    concurrency: int | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Enrich each unique domain once with a shared httpx client."""
    limit = concurrency if concurrency is not None else settings.enrich_concurrency
    semaphore = asyncio.Semaphore(limit)

    async with httpx.AsyncClient() as client:

        async def _enrich_one(domain: str) -> tuple[str, list[dict[str, str]] | BaseException]:
            async with semaphore:
                try:
                    result = await enrich_company(client, domain, job_titles, max_contacts)
                    return domain, result
                except Exception as exc:
                    return domain, exc

        raw_outcomes = await asyncio.gather(
            *[_enrich_one(domain) for domain in domains_with_rows],
            return_exceptions=True,
        )

    results: dict[str, list[dict[str, str]]] = {}
    for outcome in raw_outcomes:
        if isinstance(outcome, BaseException):
            continue
        domain, value = outcome
        if isinstance(value, BaseException):
            logger.warning("batch_enrich failed for domain=%s: %s", domain, value)
            results[domain] = []
        else:
            results[domain] = value

    return results

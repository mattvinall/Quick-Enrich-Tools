import asyncio
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_CONTACT_FIELDS = ("title", "first_name", "last_name", "email", "phone", "linkedin_url")


async def enrich_company(
    client: httpx.AsyncClient,
    domain: str,
    job_titles: list[str],
    max_contacts: int = 1,
) -> list[dict[str, str]]:
    """Fetch contacts from QuickEnrich for a single domain.

    Iterates over each job title and queries the dataset-search endpoint.
    Returns a flat list of contact dicts with keys: title, first_name,
    last_name, email, phone, linkedin_url.  On per-title errors the title
    is skipped and processing continues.
    """
    contacts: list[dict[str, str]] = []

    for title in job_titles:
        try:
            response = await client.get(
                "https://app.quickenrich.io/api/employees/dataset-search",
                params={"company_url": domain, "title": title},
                headers={"Authorization": f"Bearer {settings.quickenrich_api_key}"},
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                raw_results: list[dict[str, object]] = data
            else:
                raw_results = data.get("results", [])

            for record in raw_results[:max_contacts]:
                contacts.append(
                    {
                        "title": str(record.get("title") or title),
                        "first_name": str(record.get("first_name") or ""),
                        "last_name": str(record.get("last_name") or ""),
                        "email": str(record.get("email") or ""),
                        "phone": str(record.get("phone") or ""),
                        "linkedin_url": str(record.get("linkedin_url") or ""),
                    }
                )
        except Exception as exc:
            logger.warning("enrich_company error for domain=%s title=%s: %s", domain, title, exc)
            continue

    return contacts


async def batch_enrich(
    domains_with_rows: dict[str, list[int]],
    job_titles: list[str],
    max_contacts: int = 1,
    concurrency: int | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Enrich each unique domain once, respecting a concurrency semaphore.

    Args:
        domains_with_rows: Mapping of domain -> list of row indices that share
            that domain (used only to identify unique domains here).
        job_titles: Job titles to search for at each domain.
        max_contacts: Maximum contacts to collect per job title.
        concurrency: Max simultaneous requests; falls back to settings value.

    Returns:
        Mapping of domain -> list of contact dicts.
    """
    limit = concurrency if concurrency is not None else settings.enrich_concurrency
    semaphore = asyncio.Semaphore(limit)

    async def _enrich_one(domain: str) -> tuple[str, list[dict[str, str]] | BaseException]:
        async with semaphore:
            async with httpx.AsyncClient() as client:
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

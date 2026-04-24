import asyncio
import logging
from dataclasses import dataclass

import httpx

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.retry import retry_async

logger = logging.getLogger(__name__)

_CONTACT_FIELDS = ("title", "first_name", "last_name", "email", "phone", "mobile", "linkedin_url")

# Titles that deserve strict matching. QuickEnrich's dataset-search is substring-based,
# so asking for "CEO" returns rows like "Senior Executive Assistant, Office of the CEO"
# or "Senior Analyst, CEO Office Sales Strategy". We post-filter to drop contacts whose
# title contains a disqualifying role token when the caller asked for a C-level or founder.
_STRICT_TITLE_TOKENS = {
    "ceo", "cto", "cfo", "coo", "cmo", "cro", "cpo", "cso",
    "founder", "co-founder", "cofounder", "owner", "president",
}
_DISQUALIFYING_SUBSTRINGS = (
    "assistant",
    "analyst",
    "coordinator",
    "specialist",
    "associate",
    "intern",
    "office of the",
    "to the ",
    "executive support",
    "chief of staff",
)


def _title_matches_strict(candidate_title: str, requested_title: str) -> bool:
    """Return True if `candidate_title` is an acceptable match for `requested_title`.

    Only applies stricter filtering when the requested title is a C-level/founder/owner
    token. For everything else (e.g. "VP of Sales", "Director of Growth") we accept any
    substring match, since legitimate variants often contain words like "Director of".
    """
    cand = candidate_title.lower().strip()
    req = requested_title.lower().strip()
    if not cand:
        return False
    # Strip punctuation so "C.E.O." and "CEO," both normalise.
    cand_norm = cand.replace(".", "").replace(",", " ").replace("/", " ")
    if req not in _STRICT_TITLE_TOKENS:
        return req in cand_norm
    # Strict path: the requested token must appear, AND no disqualifying substring.
    if req not in cand_norm.split() and req not in cand_norm:
        return False
    for bad in _DISQUALIFYING_SUBSTRINGS:
        if bad in cand_norm:
            return False
    return True


def _contact_passes_title_filter(contact_title: str, requested_titles: list[str]) -> bool:
    """Accept the contact if its title matches any of the requested titles strictly."""
    if not requested_titles:
        return True
    return any(_title_matches_strict(contact_title, req) for req in requested_titles)


def _enrich_cache_key(domain: str, job_titles: list[str], max_contacts: int) -> str:
    """Build a deterministic cache key for enrichment results."""
    sorted_titles = ", ".join(sorted(t.lower() for t in job_titles))
    return make_cache_key("enrich", domain.lower(), sorted_titles, str(max_contacts))


async def enrich_company(
    client: httpx.AsyncClient,
    domain: str,
    job_titles: list[str],
    max_contacts: int = 1,
    api_key: str | None = None,
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
            headers={"Authorization": f"Bearer {api_key or settings.quickenrich_api_key}"},
            timeout=15.0,
        )
        response.raise_for_status()
        return response

    try:
        # Fire all title queries concurrently for speed
        async def _fetch_title(title: str) -> list[dict[str, object]]:
            response = await retry_async(
                lambda t=title: _do_request(t), max_retries=3, base_delay=1.0
            )
            data = response.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("data", data.get("results", []))
            return []

        all_results = await asyncio.gather(
            *[_fetch_title(t) for t in job_titles], return_exceptions=True
        )

        for raw_results in all_results:
            if isinstance(raw_results, BaseException):
                continue
            for record in raw_results:
                if len(contacts) >= max_contacts:
                    break

                record_title = str(record.get("title") or "")
                if not _contact_passes_title_filter(record_title, job_titles):
                    logger.debug(
                        "enrich_company rejected title='%s' for titles=%s on domain=%s",
                        record_title, job_titles, domain,
                    )
                    continue

                email = str(record.get("email") or "").strip()
                first = str(record.get("first_name") or "").strip()
                last = str(record.get("last_name") or "").strip()

                if email and email.upper() != "N/A":
                    dedup_key = email.lower()
                elif first or last:
                    dedup_key = f"{first}|{last}".lower()
                else:
                    dedup_key = None  # No usable key — skip dedup for this contact

                if dedup_key is not None and dedup_key in seen_keys:
                    continue
                if dedup_key is not None:
                    seen_keys.add(dedup_key)

                contacts.append(
                    {
                        "title": str(record.get("title") or ""),
                        "first_name": first,
                        "last_name": last,
                        "email": email,
                        "phone": str(record.get("employee_phone") or record.get("phone") or ""),
                        "mobile": str(
                            record.get("employee_mobile")
                            or record.get("mobile")
                            or record.get("mobile_phone")
                            or ""
                        ),
                        "linkedin_url": str(
                            record.get("employee_linkedin") or record.get("linkedin_url") or ""
                        ),
                    }
                )
            if len(contacts) >= max_contacts:
                break

        await cache_set(cache_key, {"contacts": contacts}, settings.cache_ttl_days)
    except Exception as exc:
        logger.warning(
            "enrich_company error for domain=%s titles=%s: %s: %s",
            domain, job_titles, type(exc).__name__, exc,
        )

    return contacts


@dataclass
class EnrichmentOutcome:
    """Result of enriching one domain.

    `contacts` is the list of resolved contacts (may be empty).
    `error` is non-None iff the QuickEnrich call failed for this domain; callers
    can treat an empty-but-no-error as "genuinely no matches" vs. an error as
    "retryable / surface to user".
    """
    contacts: list[dict[str, str]]
    error: str | None = None


async def batch_enrich(
    domains_with_rows: dict[str, list[int]],
    job_titles: list[str],
    max_contacts: int = 1,
    concurrency: int | None = None,
    api_key: str | None = None,
) -> dict[str, EnrichmentOutcome]:
    """Enrich each unique domain once with a shared httpx client.

    Returns {domain: EnrichmentOutcome}. An outcome with .error set means
    the QuickEnrich call failed (network/5xx/429 exhausted retries); an
    outcome with contacts=[] and error=None means the API returned no matches.
    """
    limit = concurrency if concurrency is not None else settings.enrich_concurrency
    semaphore = asyncio.Semaphore(limit)

    async with httpx.AsyncClient() as client:

        async def _enrich_one(domain: str) -> tuple[str, list[dict[str, str]] | BaseException]:
            async with semaphore:
                try:
                    result = await enrich_company(client, domain, job_titles, max_contacts, api_key=api_key)
                    return domain, result
                except Exception as exc:
                    return domain, exc

        raw_outcomes = await asyncio.gather(
            *[_enrich_one(domain) for domain in domains_with_rows],
            return_exceptions=True,
        )

    results: dict[str, EnrichmentOutcome] = {}
    for outcome in raw_outcomes:
        if isinstance(outcome, BaseException):
            logger.warning("batch_enrich outer failure: %s", outcome)
            continue
        domain, value = outcome
        if isinstance(value, BaseException):
            logger.warning(
                "batch_enrich failed for domain=%s: %s: %s",
                domain, type(value).__name__, value,
            )
            results[domain] = EnrichmentOutcome(
                contacts=[],
                error=f"{type(value).__name__}: {value}",
            )
        else:
            results[domain] = EnrichmentOutcome(contacts=value, error=None)

    return results

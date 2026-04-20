"""Optional: fetch contacts for a domain via the QuickEnrich API."""

import asyncio
import logging
import os

import httpx

from .retry import retry_async

logger = logging.getLogger(__name__)

QUICKENRICH_API_KEY = os.getenv("QUICKENRICH_API_KEY", "")


async def fetch_contacts(
    client: httpx.AsyncClient,
    domain: str,
    titles: list[str],
    max_contacts: int = 1,
) -> list[dict]:
    """Return up to max_contacts contacts matching any of the job titles."""
    if not QUICKENRICH_API_KEY:
        return []

    contacts: list[dict] = []
    seen: set[str] = set()

    async def _one(title: str) -> list[dict]:
        resp = await retry_async(
            lambda: client.get(
                "https://app.quickenrich.io/api/employees/dataset-search",
                params={"company_url": domain, "title": title},
                headers={"Authorization": f"Bearer {QUICKENRICH_API_KEY}"},
                timeout=15.0,
            ),
            max_retries=2,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("data", data.get("results", []))
        return []

    outcomes = await asyncio.gather(
        *(_one(t) for t in titles), return_exceptions=True
    )

    for raw in outcomes:
        if isinstance(raw, BaseException):
            continue
        for rec in raw:
            if len(contacts) >= max_contacts:
                break
            email = str(rec.get("email") or "").strip()
            first = str(rec.get("first_name") or "").strip()
            last = str(rec.get("last_name") or "").strip()
            key = email.lower() if email and email.upper() != "N/A" else f"{first}|{last}".lower()
            if key in seen:
                continue
            seen.add(key)
            contacts.append({
                "title": str(rec.get("title") or ""),
                "first_name": first,
                "last_name": last,
                "email": email,
                "phone": str(rec.get("employee_phone") or rec.get("phone") or ""),
                "linkedin_url": str(rec.get("employee_linkedin") or rec.get("linkedin_url") or ""),
            })
        if len(contacts) >= max_contacts:
            break

    return contacts

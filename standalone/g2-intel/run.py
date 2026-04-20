"""QuickEnrich G2 Intel — standalone CLI.

Discover companies in G2 categories → crawl their sites → extract intel → write CSV.

Usage:
    python run.py --categories product-analytics,crm --max 25 --output results.csv

Requirements:
    pip install -r requirements.txt
    cp .env.example .env   # then fill in API keys
"""

import argparse
import asyncio
import csv
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # must run before `intel/*` modules read env vars

import httpx  # noqa: E402
from tqdm.asyncio import tqdm  # noqa: E402

from intel.categories import G2_CATEGORIES  # noqa: E402
from intel.enrichment import fetch_contacts  # noqa: E402
from intel.g2 import discover_categories  # noqa: E402
from intel.llm import extract_intel  # noqa: E402
from intel.scraper import crawl_site  # noqa: E402
from intel.serper import search_company_website  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("run")

CSV_COLUMNS = [
    "company_name", "g2_url", "g2_category", "domain",
    "industry", "niche", "description", "target_market",
    "address", "phone",
    "case_studies", "website_contacts",
    "contact_first_name", "contact_last_name", "contact_title",
    "contact_email", "contact_phone", "contact_linkedin",
]


def _resolve_categories(slugs: list[str]) -> list[tuple[str, str]]:
    by_slug = {c["slug"]: c["name"] for c in G2_CATEGORIES}
    out: list[tuple[str, str]] = []
    unknown: list[str] = []
    for s in slugs:
        if s in by_slug:
            out.append((s, by_slug[s]))
        else:
            unknown.append(s)
    if unknown:
        logger.warning("Unknown categories (skipped): %s", unknown)
    return out


async def _resolve_domain(client: httpx.AsyncClient, product: dict) -> str:
    """Find a real company domain for a G2 product. Prefers scrape.do on the
    G2 product page to grab the outbound visit_website link, else Serper."""
    # Cheap path: Serper search for the product name
    try:
        dom = await search_company_website(client, product["name"])
        if dom:
            return dom
    except Exception as exc:
        logger.warning("domain resolve fail for %s: %s: %s", product["name"], type(exc).__name__, exc)
    return ""


async def _process_one(
    client: httpx.AsyncClient,
    product: dict,
    max_contacts: int,
    titles: list[str],
) -> dict:
    row = {k: "" for k in CSV_COLUMNS}
    row["company_name"] = product["name"]
    row["g2_url"] = product["g2_url"]
    row["g2_category"] = product.get("g2_category", "")

    domain = await _resolve_domain(client, product)
    row["domain"] = domain
    if not domain:
        return row

    # Crawl
    options = {"industry_description": True, "target_market": True, "company_people": True}
    pages = await crawl_site(client, domain, options)
    if not pages:
        return row

    # Extract intel
    intel = await extract_intel(domain, pages)
    if intel:
        row["industry"] = str(intel.get("industry") or "")
        row["niche"] = str(intel.get("niche") or "")
        row["description"] = str(intel.get("description") or "")
        row["target_market"] = str(intel.get("target_market") or "")
        row["address"] = str(intel.get("address") or "")
        row["phone"] = str(intel.get("phone") or "")
        row["case_studies"] = "; ".join(str(x) for x in (intel.get("case_studies") or []))
        contacts_meta = intel.get("website_contacts") or []
        row["website_contacts"] = "; ".join(
            f'{c.get("name","")} ({c.get("title","")})' for c in contacts_meta if isinstance(c, dict)
        )

    # Optional contact enrichment
    if max_contacts > 0 and titles:
        contacts = await fetch_contacts(client, domain, titles, max_contacts)
        if contacts:
            c = contacts[0]
            row["contact_first_name"] = c.get("first_name", "")
            row["contact_last_name"] = c.get("last_name", "")
            row["contact_title"] = c.get("title", "")
            row["contact_email"] = c.get("email", "")
            row["contact_phone"] = c.get("phone", "")
            row["contact_linkedin"] = c.get("linkedin_url", "")

    return row


async def main():
    p = argparse.ArgumentParser(description="QuickEnrich G2 Intel (standalone)")
    p.add_argument("--categories", required=True, help="Comma-separated G2 category slugs (e.g. product-analytics,crm)")
    p.add_argument("--max", type=int, default=25, help="Max products per category (default 25)")
    p.add_argument("--output", default="results.csv", help="Output CSV path (default results.csv)")
    p.add_argument("--concurrency", type=int, default=4, help="Company concurrency (default 4)")
    p.add_argument("--contacts", type=int, default=0, help="Contacts per company (needs QUICKENRICH_API_KEY)")
    p.add_argument("--titles", default="CEO,Founder,Co-Founder", help="Contact titles to search")
    args = p.parse_args()

    if not os.getenv("SERPER_API_KEY"):
        logger.error("SERPER_API_KEY is required (see .env.example)")
        sys.exit(1)

    slugs = [s.strip() for s in args.categories.split(",") if s.strip()]
    cats = _resolve_categories(slugs)
    if not cats:
        logger.error("No valid categories. Run: python -c \"from intel.categories import G2_CATEGORIES; [print(c['slug']) for c in G2_CATEGORIES]\"")
        sys.exit(1)

    logger.info("Discovering products across %d categories (max %d each)...", len(cats), args.max)
    t0 = time.time()
    products = await discover_categories(cats)
    # Cap per-category
    by_cat: dict[str, list[dict]] = {}
    for pr in products:
        by_cat.setdefault(pr.get("g2_category", ""), []).append(pr)
    capped: list[dict] = []
    for cat_slug, items in by_cat.items():
        capped.extend(items[: args.max])

    logger.info("Found %d products (cap %d/cat) in %.1fs", len(capped), args.max, time.time() - t0)
    if not capped:
        logger.error("No products discovered. Check SCRAPE_DO_API_KEY or try a different category.")
        sys.exit(1)

    titles = [t.strip() for t in args.titles.split(",") if t.strip()]

    sem = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient() as client:

        async def _gated(pr: dict) -> dict:
            async with sem:
                return await _process_one(client, pr, args.contacts, titles)

        rows = []
        for coro in tqdm.as_completed([_gated(pr) for pr in capped], total=len(capped), desc="enrich"):
            try:
                rows.append(await coro)
            except Exception as exc:
                logger.warning("row failed: %s: %s", type(exc).__name__, exc)

    # Write CSV
    out_path = Path(args.output)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow(row)

    found = sum(1 for r in rows if r["domain"])
    logger.info("Done. %d/%d domains resolved. Output: %s", found, len(rows), out_path.resolve())


if __name__ == "__main__":
    asyncio.run(main())

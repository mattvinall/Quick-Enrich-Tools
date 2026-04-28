"""Re-run funding enrichment from a previously-downloaded results CSV.

Skips the discovery step entirely — reads the CSV, dedupes funding events by
(company_name, funding_round), and POSTs straight to /api/v1/funding/extract.
Useful after a discovery-side bug fix to re-process the same funding events
without burning Serper /news credits again.

Auto-loads SERPER_API_KEY, QUICKENRICH_API_KEY, SCRAPE_DO_API_KEY from
backend/.env so you don't have to paste keys on the command line.

Usage:
    BACKEND_URL=https://<railway-app>.up.railway.app \\
    EMAIL=you@example.com \\
    python scripts/rerun_funding_enrichment.py path/to/funding_intel_results.csv

Override any key by exporting it explicitly — env vars beat .env values.
"""

import csv
import os
import sys
from pathlib import Path
from typing import Any

import httpx


def load_dotenv_into_os(env_path: Path) -> None:
    """Minimal .env loader — KEY=VALUE lines, comments, and quoted values.

    Skips keys already present in os.environ so explicit env vars win.
    """
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def dedupe(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Collapse N rows-per-funding-event down to one. Mirrors backend logic."""
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        name = (row.get("company_name") or "").strip()
        if not name:
            continue
        round_ = (row.get("funding_round") or "").strip()
        key = (name.lower(), round_.lower())
        entry = {
            "company_name": name,
            "funding_amount": row.get("funding_amount") or None,
            "funding_round": round_ or None,
            "lead_investor": row.get("lead_investor") or None,
            "description_snippet": row.get("funding_description") or None,
            "source_url": row.get("source_url") or None,
            "source_name": row.get("source_name") or None,
        }
        existing = seen.get(key)
        if existing is None:
            seen[key] = entry
        else:
            existing_score = sum(1 for v in existing.values() if v)
            new_score = sum(1 for v in entry.values() if v)
            if new_score > existing_score:
                seen[key] = entry
    return list(seen.values())


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    csv_path = sys.argv[1]

    # Load backend/.env so API keys are picked up without re-typing.
    backend_env = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv_into_os(backend_env)

    backend_url = os.environ["BACKEND_URL"].rstrip("/")
    email = os.environ.get("EMAIL", "matt.vinall7@gmail.com")
    serper_key = os.environ["SERPER_API_KEY"]
    quickenrich_key = os.environ["QUICKENRICH_API_KEY"]
    scrape_do_key = os.environ["SCRAPE_DO_API_KEY"]

    # utf-8-sig strips the BOM the backend writes for Excel compatibility;
    # without this, the first column header is "﻿company_name" and
    # every row.get("company_name") returns None.
    with open(csv_path, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    companies = dedupe(rows)
    print(f"Loaded {len(rows)} CSV rows -> {len(companies)} unique funding events")

    if len(companies) > 500:
        print(f"WARNING: backend caps /extract at 500 companies; trimming")
        companies = companies[:500]

    with httpx.Client(timeout=60.0) as client:
        capture_resp = client.post(
            f"{backend_url}/api/v1/email-capture",
            json={"email": email, "tool_slug": "funding-intel", "source": "rerun-script"},
        )
        capture_resp.raise_for_status()
        token = capture_resp.json()["token"]
        print(f"Captured email -> token acquired")

        extract_resp = client.post(
            f"{backend_url}/api/v1/funding/extract",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "companies": companies,
                "options": {
                    "industry_description": True,
                    "target_market": True,
                    "company_people": True,
                    "homepage_raw_text": False,
                },
                "serper_api_key": serper_key,
                "quickenrich_api_key": quickenrich_key,
                "scrape_do_api_key": scrape_do_key,
                "job_titles": ["CEO", "Founder"],
                "max_contacts": 3,
            },
        )
        if extract_resp.status_code >= 400:
            print(f"ERROR {extract_resp.status_code}: {extract_resp.text}")
            return 1
        data = extract_resp.json()

    print()
    print(f"Job created: {data['job_id']}")
    print(f"Companies queued: {data['total_companies']}")
    print(f"Job token (expires in 24h): {data['token']}")
    print()
    print(f"Watch progress at:")
    print(f"  {backend_url}/api/v1/jobs/{data['job_id']}/sse?token={data['token']}")
    print()
    print(f"Or open the funding-intel page — the saved jobId in localStorage")
    print(f"will resume the active job automatically.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

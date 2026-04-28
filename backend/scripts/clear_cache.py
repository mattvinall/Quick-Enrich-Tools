"""Ad-hoc Redis cache cleaner for QuickEnrich.

Works with local Redis, Railway's built-in Redis add-on, or Upstash — just
a plain async redis-py client that reads REDIS_URL from the environment.

Usage
-----
List known cache prefixes and quit:
    python backend/scripts/clear_cache.py --list

Clear every key under one or more prefixes (the common case):
    python backend/scripts/clear_cache.py g2_cat_scrape_v3 g2_cat
    python backend/scripts/clear_cache.py enrich linkedin

Clear everything in the DB (NUKE, requires --yes):
    python backend/scripts/clear_cache.py --all --yes

Running against production Redis
--------------------------------
Option 1 — SSH into the backend container (works even without public Redis):
    railway ssh "python /app/scripts/clear_cache.py g2_cat_scrape_v3 enrich"

Option 2 — From local, if Redis has a public TCP proxy enabled:
    REDIS_URL="redis://default:<password>@<public-host>:<port>" \\
        python backend/scripts/clear_cache.py enrich linkedin
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Make the app package importable when running via `railway run python backend/scripts/...`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import redis.asyncio as aioredis  # noqa: E402

from app.config import settings  # noqa: E402

# Prefixes the app writes to, keyed by subsystem. Kept in sync manually with
# the make_cache_key() callers across the codebase so `--list` stays useful.
KNOWN_PREFIXES = {
    "g2_cat_scrape_v3": "G2 category scrape (current)",
    "g2_cat_scrape_v2": "G2 category scrape (orphaned, pre-bump)",
    "g2_cat": "G2 Serper-fallback discovery",
    "enrich": "QuickEnrich contact enrichment",
    "linkedin": "Phase 0 LinkedIn profile search",
    "serper": "Serper domain/company search",
    "scrape": "scrape.do fetched homepages",
    "intel": "LLM extracted company intel (industry/description/etc.)",
    "funding_discovery": "Funded-companies-today discovery results",
}

BATCH = 500  # keys per DEL call — Redis handles several thousand fine but 500 is polite


async def clear_prefix(client: aioredis.Redis, prefix: str) -> int:
    """Delete every key under `{prefix}:*`. Returns the count removed."""
    deleted = 0
    pipe: list[str] = []
    async for key in client.scan_iter(match=f"{prefix}:*", count=BATCH):
        pipe.append(key)
        if len(pipe) >= BATCH:
            deleted += await client.delete(*pipe)
            pipe.clear()
    if pipe:
        deleted += await client.delete(*pipe)
    return deleted


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefixes", nargs="*", help="Cache prefixes to clear.")
    parser.add_argument("--list", action="store_true", help="List known prefixes and exit.")
    parser.add_argument("--all", action="store_true", help="FLUSHDB the whole cache DB.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation for --all.")
    args = parser.parse_args()

    if args.list:
        print("Known cache prefixes:")
        for prefix, desc in KNOWN_PREFIXES.items():
            print(f"  {prefix:<22}  {desc}")
        return 0

    if not args.prefixes and not args.all:
        parser.print_help()
        return 2

    redis_host = settings.redis_url.split("@", 1)[-1].split("/", 1)[0] or "(local)"
    print(f"Connecting to Redis at {redis_host}...")
    client = aioredis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)

    try:
        await client.ping()
    except Exception as exc:
        print(f"Failed to connect: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    total = 0
    try:
        if args.all:
            if not args.yes:
                print("Refusing to FLUSHDB without --yes. Re-run with --all --yes to nuke.", file=sys.stderr)
                return 2
            await client.flushdb()
            print("FLUSHDB issued — entire DB cleared.")
            return 0

        for prefix in args.prefixes:
            count = await clear_prefix(client, prefix)
            total += count
            print(f"  {prefix:<22}  -> deleted {count} keys")

        print(f"\nDone. Removed {total} keys total.")
        return 0
    finally:
        await client.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

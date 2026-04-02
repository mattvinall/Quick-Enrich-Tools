"""Google Maps to Company Intel pipeline.

Phase 0: Search Google Maps via Serper to discover businesses.
Phases 1-5: Delegates to existing intel pipeline (Resolve -> Crawl -> Extract -> Enrich -> Deliver).
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Job, JobResult
from app.services.serper import batch_search_maps
from app.workers.intel_pipeline import run_intel_pipeline, update_job_progress

logger = logging.getLogger(__name__)

_INSERT_BATCH_SIZE = 1000


async def run_maps_pipeline(ctx: dict, job_id: str) -> None:
    """Main entry point for the Maps Intel pipeline.

    Phase 0: Search Google Maps to discover businesses, create JobResult rows.
    Phases 1-5: Delegate to existing intel pipeline.
    """
    parsed_job_id = uuid.UUID(job_id)

    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        config = job.config or {}

        job.status = "maps_searching"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # ── Phase 0: Maps Discovery ─────────────────────────────────────
    searches: list[dict[str, str]] = config.get("searches", [])
    max_per_search: int = config.get("max_per_search", 20)

    logger.info(
        "Maps pipeline starting for job_id=%s: %d searches, max_per_search=%d",
        job_id, len(searches), max_per_search,
    )

    try:
        places = await batch_search_maps(
            searches, max_per_search=max_per_search,
        )
    except Exception as exc:
        logger.exception("Maps search failed for job_id=%s: %s", job_id, exc)
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "failed"
            job.error_message = f"Maps search failed: {exc}"
            await db.commit()
        raise

    if not places:
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "failed"
            job.error_message = "No businesses found for the given search terms and location."
            await db.commit()
        return

    # ── Create JobResult rows in sub-batches ─────────────────────────
    def _extract_domain(url: str) -> str:
        url = url.strip().lower()
        for prefix in ("https://", "http://"):
            if url.startswith(prefix):
                url = url[len(prefix):]
                break
        if url.startswith("www."):
            url = url[4:]
        for sep in ("/", "?", "#"):
            idx = url.find(sep)
            if idx != -1:
                url = url[:idx]
        return url

    async with AsyncSessionLocal() as db:
        for batch_start in range(0, len(places), _INSERT_BATCH_SIZE):
            batch = places[batch_start:batch_start + _INSERT_BATCH_SIZE]
            job_results = []
            for i, p in enumerate(batch):
                website = str(p.get("website") or "")
                domain = _extract_domain(website) if website else ""
                cid = str(p.get("cid") or "")
                maps_url = f"https://www.google.com/maps/place/?cid={cid}" if cid else ""

                job_results.append(
                    JobResult(
                        job_id=parsed_job_id,
                        row_index=batch_start + i,
                        input_data={
                            "input": website or str(p.get("title", "")),
                            "input_type": "url" if website else "name",
                            "search_term": str(p.get("search_term", "")),
                            "location": str(p.get("location", "")),
                            "business_name": str(p.get("title", "")),
                            "category": str(p.get("category", "")),
                            "maps_address": str(p.get("address", "")),
                            "maps_phone": str(p.get("phoneNumber", "")),
                            "rating": p.get("rating"),
                            "review_count": p.get("ratingCount"),
                            "latitude": p.get("latitude"),
                            "longitude": p.get("longitude"),
                            "google_cid": cid,
                            "google_maps_url": maps_url,
                        },
                        raw_domain=domain or None,
                        status="pending",
                    )
                )
            db.add_all(job_results)
            await db.flush()

        # Update job with actual count
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        job.total_rows = len(places)
        await db.commit()

    logger.info(
        "Maps Phase 0 complete for job_id=%s: %d businesses discovered",
        job_id, len(places),
    )

    try:
        async with AsyncSessionLocal() as progress_db:
            await update_job_progress(
                progress_db, parsed_job_id, "maps_search",
                len(searches), len(searches),
                processed_rows=0,
            )
    except Exception:
        pass

    # ── Phases 1-5: Delegate to existing intel pipeline ──────────────
    await run_intel_pipeline({}, job_id)

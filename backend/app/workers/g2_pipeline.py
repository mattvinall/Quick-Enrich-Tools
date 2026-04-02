"""G2 Category to Company Intel pipeline.

Phase 0: Scrape G2 categories to discover companies.
Phases 1-5: Delegates to existing intel pipeline (Resolve → Crawl → Extract → Enrich → Deliver).
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Job, JobResult
from app.services.g2_scraper import batch_scrape_g2_categories
from app.workers.intel_pipeline import run_intel_pipeline, update_job_progress

logger = logging.getLogger(__name__)

_INSERT_BATCH_SIZE = 1000


async def run_g2_pipeline(ctx: dict, job_id: str) -> None:
    """Main entry point for the G2 Intel pipeline.

    Phase 0: Scrape G2 categories to discover companies, create JobResult rows.
    Phases 1-5: Delegate to existing intel pipeline.
    """
    parsed_job_id = uuid.UUID(job_id)

    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        config = job.config or {}

        job.status = "g2_scraping"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # ── Phase 0: G2 Scrape ──────────────────────────────────────────
    categories: list[str] = config.get("categories", [])
    max_per_category: int = config.get("max_per_category", 250)
    max_total: int = settings.g2_max_total_companies

    logger.info(
        "G2 pipeline starting for job_id=%s: %d categories, max_per_category=%d",
        job_id, len(categories), max_per_category,
    )

    async def _on_g2_progress(done: int, total: int) -> None:
        try:
            async with AsyncSessionLocal() as progress_db:
                await update_job_progress(progress_db, parsed_job_id, "g2_scrape", done, total)
        except Exception:
            pass

    try:
        products = await batch_scrape_g2_categories(
            categories, max_per_category, on_progress=_on_g2_progress
        )
    except Exception as exc:
        logger.exception("G2 scrape failed for job_id=%s: %s", job_id, exc)
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "failed"
            job.error_message = f"G2 scrape failed: {exc}"
            await db.commit()
        raise

    # Enforce total cap
    if len(products) > max_total:
        products = products[:max_total]
        logger.info("G2 pipeline: capped to %d companies", max_total)

    if not products:
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "failed"
            job.error_message = "No companies found in selected G2 categories."
            await db.commit()
        return

    # ── Create JobResult rows in sub-batches ─────────────────────────
    async with AsyncSessionLocal() as db:
        for batch_start in range(0, len(products), _INSERT_BATCH_SIZE):
            batch = products[batch_start:batch_start + _INSERT_BATCH_SIZE]
            job_results = [
                JobResult(
                    job_id=parsed_job_id,
                    row_index=batch_start + i,
                    input_data={
                        "input": p.get("website") or p["name"],
                        "input_type": "url" if p.get("website") else "name",
                        "company_name": p["name"],
                        "g2_url": p.get("g2_url", ""),
                        "g2_category": p.get("g2_category", ""),
                        "g2_rating": p.get("rating"),
                        "g2_review_count": p.get("review_count"),
                    },
                    status="pending",
                )
                for i, p in enumerate(batch)
            ]
            db.add_all(job_results)
            await db.flush()

        # Update job with actual count
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        job.total_rows = len(products)
        await db.commit()

    logger.info(
        "G2 Phase 0 complete for job_id=%s: %d companies discovered",
        job_id, len(products),
    )

    try:
        async with AsyncSessionLocal() as progress_db:
            await update_job_progress(
                progress_db, parsed_job_id, "g2_scrape",
                len(categories), len(categories),
                processed_rows=0,
            )
    except Exception:
        pass

    # ── Phases 1-5: Delegate to existing intel pipeline ──────────────
    await run_intel_pipeline({}, job_id)

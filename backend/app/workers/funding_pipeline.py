"""Funded Companies Today pipeline.

Phase 0: Create JobResult rows from user-selected funded companies.
Phases 1-5: Delegates to existing intel pipeline (Resolve -> Crawl -> Extract -> Enrich -> Deliver).
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Job, JobResult
from app.workers.intel_pipeline import run_intel_pipeline, update_job_progress

logger = logging.getLogger(__name__)

_INSERT_BATCH_SIZE = 1000


async def run_funding_pipeline(ctx: dict, job_id: str) -> None:
    """Main entry point for the Funding Intel pipeline."""
    parsed_job_id = uuid.UUID(job_id)

    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        config = job.config or {}

        job.status = "funding_discovering"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    companies: list[dict] = config.get("companies", [])

    if not companies:
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "failed"
            job.error_message = "No companies provided."
            await db.commit()
        return

    logger.info("Funding pipeline starting for job_id=%s: %d companies", job_id, len(companies))

    # ── Phase 0: Create JobResult rows ──────────────────────────────
    async with AsyncSessionLocal() as db:
        for batch_start in range(0, len(companies), _INSERT_BATCH_SIZE):
            batch = companies[batch_start:batch_start + _INSERT_BATCH_SIZE]
            job_results = []
            for i, c in enumerate(batch):
                job_results.append(
                    JobResult(
                        job_id=parsed_job_id,
                        row_index=batch_start + i,
                        input_data={
                            "input": str(c.get("company_name", "")),
                            "input_type": "name",
                            "company_name": str(c.get("company_name", "")),
                            "funding_amount": c.get("funding_amount"),
                            "funding_round": str(c.get("funding_round", "")),
                            "lead_investor": c.get("lead_investor"),
                            "funding_description": c.get("description_snippet"),
                            "source_url": str(c.get("source_url", "")),
                            "source_name": str(c.get("source_name", "")),
                        },
                        status="pending",
                    )
                )
            db.add_all(job_results)
            await db.flush()

        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        job.total_rows = len(companies)
        await db.commit()

    logger.info("Funding Phase 0 complete for job_id=%s: %d companies", job_id, len(companies))

    try:
        async with AsyncSessionLocal() as progress_db:
            await update_job_progress(
                progress_db, parsed_job_id, "funding_discover",
                len(companies), len(companies),
                processed_rows=0,
            )
    except Exception:
        pass

    # ── Phases 1-5: Delegate to existing intel pipeline ─────────────
    await run_intel_pipeline({}, job_id)

"""People Intel pipeline.

Phase 0: Search LinkedIn profiles via Serper.
Phases 1-5: Delegates to existing intel pipeline (Resolve → Crawl → Extract → Enrich → Deliver).
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Job, JobResult
from app.services.linkedin_search import batch_linkedin_search
from app.workers.intel_pipeline import run_intel_pipeline, update_job_progress

logger = logging.getLogger(__name__)

_BATCH_SIZE = 200


async def run_people_pipeline(ctx: dict, job_id: str) -> None:
    """Main entry point for the People Intel pipeline.

    Phase 0: Search LinkedIn profiles for each person.
    Phases 1-5: Delegate to existing intel pipeline.
    """
    parsed_job_id = uuid.UUID(job_id)

    async with AsyncSessionLocal() as db:
        job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
        job = job_result.scalar_one()
        config = job.config or {}
        total_rows = job.total_rows

        job.status = "linkedin_searching"
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    serper_api_key = config.get("serper_api_key") or None

    logger.info(
        "People pipeline starting for job_id=%s: %d rows",
        job_id, total_rows,
    )

    # ── Phase 0: LinkedIn Search ───────────────────────────────────
    try:
        async with AsyncSessionLocal() as db:
            await update_job_progress(db, parsed_job_id, "linkedin_search", 0, total_rows)

        searched = 0
        for batch_start in range(0, total_rows, _BATCH_SIZE):
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(JobResult)
                    .where(JobResult.job_id == parsed_job_id)
                    .order_by(JobResult.row_index)
                    .offset(batch_start)
                    .limit(_BATCH_SIZE)
                )
                batch_results = list(result.scalars().all())
                if not batch_results:
                    break

                # Build search rows
                search_rows = []
                for r in batch_results:
                    input_data = r.input_data or {}
                    search_rows.append({
                        "full_name": input_data.get("full_name", ""),
                        "company_name": input_data.get("company_name", ""),
                    })

                # Batch search LinkedIn
                outcomes = await batch_linkedin_search(
                    search_rows,
                    concurrency=settings.linkedin_search_concurrency,
                    api_key=serper_api_key,
                )

                # Update results
                outcome_by_idx = {o["row_index"]: o for o in outcomes}
                for i, r in enumerate(batch_results):
                    outcome = outcome_by_idx.get(i, {})
                    linkedin_url = outcome.get("linkedin_url", "")
                    confidence = outcome.get("confidence", 0.0)
                    search_result = outcome.get("search_results")

                    r.search_results = {
                        "linkedin_url": linkedin_url,
                        "confidence": confidence,
                        **(search_result or {}),
                    }

                    if linkedin_url:
                        r.status = "found"
                    else:
                        r.status = "not_found"

                    # Set up input for intel pipeline resolve phase:
                    # If user provided website, use it directly as URL input
                    # Otherwise, use company_name for Serper domain resolution
                    input_data = r.input_data or {}
                    website = input_data.get("website", "")
                    if website:
                        r.input_data = {
                            **input_data,
                            "input": website,
                            "input_type": "url",
                        }
                    else:
                        r.input_data = {
                            **input_data,
                            "input": input_data.get("company_name", ""),
                            "input_type": "name",
                        }

                    # Reset status back to pending for intel pipeline phases
                    r.status = "pending"

                await db.commit()

                searched += len(batch_results)
                await update_job_progress(db, parsed_job_id, "linkedin_search", searched, total_rows)

        logger.info(
            "People Phase 0 complete for job_id=%s: %d LinkedIn searches done",
            job_id, searched,
        )

    except Exception as exc:
        logger.exception("People LinkedIn search failed for job_id=%s: %s", job_id, exc)
        async with AsyncSessionLocal() as db:
            job_result = await db.execute(select(Job).where(Job.id == parsed_job_id))
            job = job_result.scalar_one()
            job.status = "failed"
            job.error_message = f"LinkedIn search failed: {exc}"
            await db.commit()
        raise

    # ── Phases 1-5: Delegate to existing intel pipeline ────────────
    await run_intel_pipeline({}, job_id)

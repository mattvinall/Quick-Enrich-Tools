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
        "People pipeline starting for job_id=%s: %d rows, user_serper_key=%s",
        job_id, total_rows, "provided" if serper_api_key else "using-server-fallback",
    )

    # ── Phase 0: LinkedIn Search ───────────────────────────────────
    try:
        async with AsyncSessionLocal() as db:
            await update_job_progress(db, parsed_job_id, "linkedin_search", 0, total_rows)

        searched = 0
        linkedin_found_count = 0
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
                    if linkedin_url:
                        linkedin_found_count += 1
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
                    # Otherwise, use company_name for Serper domain resolution.
                    #
                    # Stash the Phase 0 LinkedIn result in input_data too — the
                    # intel pipeline's resolve phase overwrites r.search_results
                    # with its own domain-lookup payload, which was silently
                    # wiping the LinkedIn URL from the final CSV. input_data is
                    # only ever read (never mutated) downstream, so it's safe.
                    input_data = r.input_data or {}
                    website = input_data.get("website", "")
                    base_input = {
                        **input_data,
                        "linkedin_url": linkedin_url,
                        "linkedin_confidence": confidence,
                    }
                    if website:
                        r.input_data = {
                            **base_input,
                            "input": website,
                            "input_type": "url",
                        }
                    else:
                        r.input_data = {
                            **base_input,
                            "input": base_input.get("company_name", ""),
                            "input_type": "name",
                        }

                    # Reset status back to pending for intel pipeline phases
                    r.status = "pending"

                await db.commit()

                searched += len(batch_results)
                await update_job_progress(db, parsed_job_id, "linkedin_search", searched, total_rows)

        logger.info(
            "People Phase 0 complete for job_id=%s: %d searches done, %d LinkedIn URLs found (%.0f%% hit rate)",
            job_id, searched, linkedin_found_count,
            (linkedin_found_count / searched * 100) if searched else 0.0,
        )
        if searched > 0 and linkedin_found_count == 0:
            # Zero hits across the whole batch usually means the Serper key is
            # misconfigured or the query pattern mismatches. Surface it loudly
            # so operators can tell "no matches" apart from "silent failure".
            logger.warning(
                "People Phase 0: zero LinkedIn hits across %d rows for job_id=%s. "
                "Check Serper key validity and Phase 0 LINKEDIN SEARCH logs above.",
                searched, job_id,
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
